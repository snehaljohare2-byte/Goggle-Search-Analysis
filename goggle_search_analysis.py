
#A lightweight Streamlit app that uses pytrends (Google Trends) to analyze search interest:
# Compare search interest for multiple keywords (interest over time)
#Display popularity by country/region
# Show interest by subregion (map/table)
# Show related queries (rising & top)
# Export results as CSV

#Dependencies:
   # pip install streamlit pytrends pandas matplotlib plotly

#Run:
   # streamlit run google_search_analysis.py

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from pytrends.request import TrendReq
import io
import plotly.express as px

# --- Helper setup ---
@st.cache_data(ttl=3600)
def init_pytrends(hl="en-US", tz=360):
    return TrendReq(hl=hl, tz=tz)

def build_payload(pytrends, kw_list, timeframe, geo="", cat=0):
    pytrends.build_payload(kw_list, timeframe=timeframe, geo=geo, cat=cat)

def fetch_interest_over_time(pytrends, kw_list, timeframe, geo="", cat=0):
    build_payload(pytrends, kw_list, timeframe, geo, cat)
    df = pytrends.interest_over_time()
    if df.empty:
        return pd.DataFrame()
    # drop isPartial column if present
    df = df.reset_index()
    if 'isPartial' in df.columns:
        df = df.drop(columns=['isPartial'])
    return df

def fetch_interest_by_region(pytrends, kw_list, timeframe, geo="", resolution='COUNTRY', cat=0):
    build_payload(pytrends, kw_list, timeframe, geo, cat)
    # resolution can be 'COUNTRY' or 'REGION' or 'CITY'
    return pytrends.interest_by_region(resolution=resolution)

def fetch_related_queries(pytrends, kw_list, timeframe, geo="", cat=0):
    build_payload(pytrends, kw_list, timeframe, geo, cat)
    return pytrends.related_queries()

def df_to_csv_bytes(df):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf

# Streamlit Layout 
st.set_page_config(page_title="Google Search Analysis", layout="wide")
st.title("Google Search Analysis (Google Trends)")

with st.sidebar:
    st.header("Settings")
    default_keywords = st.text_input("Enter keywords (comma-separated)", value="python, java, javascript")
    timeframe = st.selectbox("Timeframe", options=[
        "today 12-m", "today 3-m", "today 1-m", "now 7-d", "all"
    ], index=0)
    geo = st.text_input("Geo (country code, e.g. US, IN) — leave blank for worldwide", value="")
    resolution = st.selectbox("Region resolution for maps/tables", options=["COUNTRY", "REGION", "CITY"], index=0)
    cat = st.number_input("Category (0 = all)", min_value=0, max_value=700, value=0, step=1)
    run_btn = st.button("Run analysis")

st.markdown("### Notes")
st.markdown("- This app uses *pytrends* (an unofficial Google Trends API). If Google blocks requests, try later or reduce frequency.")
st.markdown("- For very large keyword lists or frequent queries, Google may throttle you.")

if run_btn:
    keywords = [k.strip() for k in default_keywords.split(",") if k.strip()]
    if not keywords:
        st.error("Please enter at least one keyword.")
    else:
        st.info(f"Fetching Trends data for: {', '.join(keywords)} — timeframe: {timeframe} — geo: {geo or 'WORLDWIDE'}")
        try:
            pytrends = init_pytrends()
            # Interest over time
            iot = fetch_interest_over_time(pytrends, keywords, timeframe, geo, cat)
            if iot.empty:
                st.warning("No data returned for the chosen parameters. Try a different timeframe or keywords.")
            else:
                st.subheader("Interest over time")
                st.write("Interactive table:")
                st.dataframe(iot, use_container_width=True)

                # Matplotlib plot (one figure)
                fig, ax = plt.subplots(figsize=(10, 4))
                for kw in keywords:
                    if kw in iot.columns:
                        ax.plot(iot['date'], iot[kw], label=kw)
                ax.set_xlabel("Date")
                ax.set_ylabel("Interest (0-100)")
                ax.legend()
                ax.grid(True)
                st.pyplot(fig)

                # Allow CSV download
                csv_bytes = df_to_csv_bytes(iot)
                st.download_button("Download interest_over_time CSV", data=csv_bytes, file_name="interest_over_time.csv", mime="text/csv")

            # Interest by region
            st.subheader("Interest by region")
            try:
                iregion = fetch_interest_by_region(pytrends, keywords, timeframe, geo, resolution, cat)
                if iregion is None or iregion.empty:
                    st.warning("No region data available.")
                else:
                    # Show top 20 regions
                    top_regions = iregion.sort_values(by=keywords[0], ascending=False).head(20).reset_index()
                    st.dataframe(top_regions, use_container_width=True)

                    # If resolution is COUNTRY or REGION, use plotly choropleth for countries
                    if resolution == 'COUNTRY' and 'geoName' in top_regions.columns:
                        # rename columns for plotly
                        # expect top_regions to have index as geoName or use the index name
                        col_to_plot = keywords[0] if keywords[0] in top_regions.columns else top_regions.columns[-1]
                        # Try to use country codes — pytrends usually returns region names, not ISO codes.
                        # We'll attempt a simple choropleth if country names are present.
                        try:
                            fig2 = px.choropleth(top_regions, locations='geoName', locationmode='country names',
                                                 color=col_to_plot, hover_name='geoName',
                                                 title=f"Top regions for {col_to_plot}")
                            st.plotly_chart(fig2, use_container_width=True)
                        except Exception:
                            st.info("Could not render world map — showing table instead.")
            except Exception as e:
                st.error(f"Error fetching region data: {e}")

            # Related queries
            st.subheader("Related queries")
            try:
                related = fetch_related_queries(pytrends, keywords, timeframe, geo, cat)
                # related is a dict: keyword -> {'rising': df, 'top': df}
                for kw in keywords:
                    st.markdown(f"*{kw}*")
                    if kw in related and related[kw] is not None:
                        r = related[kw]
                        top_df = r.get('top')
                        rising_df = r.get('rising')
                        if top_df is not None and not top_df.empty:
                            st.write("Top related queries")
                            st.dataframe(top_df.head(10))
                            buf = df_to_csv_bytes(top_df.reset_index())
                            st.download_button(f"Download {kw} top related CSV", data=buf, file_name=f"{kw}related_top.csv", mime="text/csv", key=f"dl_top{kw}")
                        if rising_df is not None and not rising_df.empty:
                            st.write("Rising related queries")
                            st.dataframe(rising_df.head(10))
                            buf2 = df_to_csv_bytes(rising_df.reset_index())
                            st.download_button(f"Download {kw} rising related CSV", data=buf2, file_name=f"{kw}related_rising.csv", mime="text/csv", key=f"dl_rising{kw}")
                    else:
                        st.write("No related queries returned.")
            except Exception as e:
                st.error(f"Error fetching related queries: {e}")

            st.success("Analysis complete.")
        except Exception as ex:
            st.error(f"An error occurred: {ex}")
            st.write("Tip: make sure you have internet access and pytrends installed.")