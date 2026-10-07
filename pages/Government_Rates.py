import re
from html.parser import HTMLParser
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from auth import require_role


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Government Grocery Rates",
    page_icon="🏛️",
    layout="wide",
)

require_role("Sales Boy", "Manager", "Admin")


# =========================================================
# GOVERNMENT SOURCE
# =========================================================

GOVT_URL = "https://fcainfoweb.nic.in/Default.aspx"

RETAIL_TITLE = "All India Average Retail Price"
WHOLESALE_TITLE = "All India Average Wholesale Price"


def extract_date(text: str, title: str) -> str:
    pattern = (
        rf"{re.escape(title)}.*?As on\s+"
        rf"(\d{{2}}/\d{{2}}/\d{{4}})"
    )

    match = re.search(
        pattern,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    return match.group(1) if match else ""


def parse_section_tables(
    html: str,
    start_title: str,
    end_title: str | None = None,
):
    """
    Read commodity tables from the official Department of Consumer
    Affairs Price Monitoring System page.
    """

    start = re.search(
        re.escape(start_title),
        html,
        flags=re.IGNORECASE,
    )

    if not start:
        return []

    section_start = start.start()

    if end_title:
        end = re.search(
            re.escape(end_title),
            html[start.end():],
            flags=re.IGNORECASE,
        )

        section_end = (
            start.end() + end.start()
            if end
            else len(html)
        )
    else:
        section_end = len(html)

    section_html = html[section_start:section_end]

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_table = False
            self.in_row = False
            self.in_cell = False
            self.current_cell = []
            self.current_row = []
            self.tables = []
            self.current_table = []

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()

            if tag == "table":
                self.in_table = True
                self.current_table = []

            elif self.in_table and tag == "tr":
                self.in_row = True
                self.current_row = []

            elif self.in_row and tag in ("td", "th"):
                self.in_cell = True
                self.current_cell = []

            elif self.in_cell and tag == "br":
                self.current_cell.append(" ")

        def handle_data(self, data):
            if self.in_cell:
                self.current_cell.append(data)

        def handle_endtag(self, tag):
            tag = tag.lower()

            if tag in ("td", "th") and self.in_cell:
                value = re.sub(
                    r"\\s+",
                    " ",
                    "".join(self.current_cell),
                ).strip()

                self.current_row.append(value)
                self.current_cell = []
                self.in_cell = False

            elif tag == "tr" and self.in_row:
                if self.current_row:
                    self.current_table.append(self.current_row)
                self.current_row = []
                self.in_row = False

            elif tag == "table" and self.in_table:
                if self.current_table:
                    self.tables.append(self.current_table)
                self.current_table = []
                self.in_table = False

    parser = TableParser()
    parser.feed(section_html)

    rows = []

    for table in parser.tables:
        for table_row in table:
            if len(table_row) < 2:
                continue

            commodity = str(table_row[0]).strip()
            price_raw = str(table_row[1]).strip()

            if (
                not commodity
                or commodity.lower() in {
                    "commodity",
                    "prices",
                    "price",
                    "nan",
                }
            ):
                continue

            # Keep only rows whose second column contains a numeric price.
            numeric_text = re.sub(
                r"[^0-9.\\-]",
                "",
                price_raw.replace(",", ""),
            )

            try:
                numeric = float(numeric_text)
            except (TypeError, ValueError):
                continue

            rows.append(
                {
                    "Commodity": commodity,
                    "Price": numeric,
                }
            )

    return rows


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_government_rates():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/154 Safari/537.36"
        )
    }

    response = requests.get(
        GOVT_URL,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    html = response.text

    page_text = re.sub(r"<[^>]+>", " ", html)
    page_text = re.sub(r"\s+", " ", page_text)

    retail_rows = parse_section_tables(
        html,
        RETAIL_TITLE,
        WHOLESALE_TITLE,
    )

    wholesale_rows = parse_section_tables(
        html,
        WHOLESALE_TITLE,
    )

    retail_df = pd.DataFrame(retail_rows)
    wholesale_df = pd.DataFrame(wholesale_rows)

    if retail_df.empty:
        raise RuntimeError(
            "Could not read Government retail rates "
            "from the official website."
        )

    if wholesale_df.empty:
        raise RuntimeError(
            "Could not read Government wholesale rates "
            "from the official website."
        )

    return {
        "retail": retail_df,
        "wholesale": wholesale_df,
        "retail_date": extract_date(
            page_text,
            RETAIL_TITLE,
        ),
        "wholesale_date": extract_date(
            page_text,
            WHOLESALE_TITLE,
        ),
        "fetched_at": datetime.now().strftime(
            "%d-%m-%Y %I:%M %p"
        ),
    }


# =========================================================
# PAGE
# =========================================================

st.title("🏛️ Government Grocery Rates")

st.caption(
    "Government of India — Department of Consumer Affairs "
    "Price Monitoring System"
)

try:
    data = fetch_government_rates()

except Exception as exc:
    st.error("Unable to retrieve Government grocery rates.")

    st.warning(
        "The official Government website may be temporarily "
        "unavailable or its page format may have changed."
    )

    st.exception(exc)
    st.stop()


col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    st.success(
        "Retail rates: "
        f"{data['retail_date'] or 'Latest available'}"
    )

with col2:
    st.info(
        "Wholesale rates: "
        f"{data['wholesale_date'] or 'Latest available'}"
    )

with col3:
    if st.button(
        "🔄 Refresh Rates",
        use_container_width=True,
    ):
        fetch_government_rates.clear()
        st.rerun()


st.divider()


def show_rate_table(df, unit_label, key_suffix):
    search = st.text_input(
        "🔎 Search commodity",
        placeholder="Rice, sugar, dal, oil...",
        key=f"rate_search_{key_suffix}",
    )

    filtered = df.copy()

    if search.strip():
        filtered = filtered[
            filtered["Commodity"].str.contains(
                search.strip(),
                case=False,
                na=False,
            )
        ]

    display_df = filtered.rename(
        columns={
            "Commodity": "Commodity",
            "Price": f"Rate ({unit_label})",
        }
    )

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Commodity": st.column_config.TextColumn(
                "Commodity",
                width="large",
            ),
            f"Rate ({unit_label})": st.column_config.NumberColumn(
                f"Rate ({unit_label})",
                format="₹ %.2f",
            ),
        },
    )

    st.caption(
        f"Showing {len(filtered)} of {len(df)} commodities."
    )


tab_retail, tab_wholesale = st.tabs(
    ["🛒 Retail Rates", "📦 Wholesale Rates"]
)

with tab_retail:
    st.subheader("All India Average Retail Price")
    show_rate_table(
        data["retail"],
        "per Kg",
        "retail",
    )

with tab_wholesale:
    st.subheader("All India Average Wholesale Price")
    show_rate_table(
        data["wholesale"],
        "per Qtl.",
        "wholesale",
    )


st.divider()

st.subheader("ℹ️ Important")

st.info(
    "These are Government of India All-India average reference "
    "prices. They are not necessarily the actual retail price "
    "in Berhampur/Odisha. Commodity quality and variety can "
    "differ between monitored centres."
)

st.caption(
    "Source: Department of Consumer Affairs — "
    "Price Monitoring System | "
    f"Retrieved: {data['fetched_at']}"
)

st.markdown(
    f"[Open official Government Price Monitoring System]({GOVT_URL})"
)
