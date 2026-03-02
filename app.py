import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="番茄價格 AI 預報站", layout="wide", page_icon="??")

@st.cache_data(ttl=3600)
def get_data():
    url = "https://data.moa.gov.tw"
    try:
        r = requests.get(url)
        df = pd.DataFrame(r.json())
        df = df[df['作物名稱'].str.contains('番茄', na=False)].copy()
        df['平均價'] = pd.to_numeric(df['平均價'])
        df['交易量'] = pd.to_numeric(df['交易量'])
        return df
    except:
        return pd.DataFrame({"作物名稱":["資料連線中..."], "平均價":[0], "交易量":[0]})

def predict_logic(current_price, vol, is_fest):
    base = current_price
    vol_factor = -0.01 * (vol - 500)
    fest_factor = 12.5 if is_fest else 0
    preds = [round(base + vol_factor + fest_factor + (i * 0.5), 1) for i in range(7)]
    return preds

st.title("?? 番茄價格未來 7 天預測系統")
data = get_data()

with st.sidebar:
    st.header("?? 參數設定")
    target = st.selectbox("選擇品種", data['作物名稱'].unique())
    row = data[data['作物名稱'] == target].iloc[0]
    sim_vol = st.slider("預估未來到貨量", 50, 1500, int(row['交易量']))
    sim_fest = st.checkbox("是否鄰近節慶")
    btn = st.button("啟動 AI 預測", type="primary")

if btn:
    future_prices = predict_logic(row['平均價'], sim_vol, sim_fest)
    dates = [(datetime.now() + timedelta(days=i)).strftime("%m/%d") for i in range(7)]
    fig = px.line(x=dates, y=future_prices, text=future_prices, title=f"{target} 趨勢預測")
    st.plotly_chart(fig, use_container_width=True)
    st.metric("今日行情", f"{row['平均價']} 元", delta=f"預測 7 天後: {future_prices[-1]} 元")
else:
    st.info("請點擊左側『啟動 AI 預測』按鈕")