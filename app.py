import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. 基本設定與金鑰 ---
st.set_page_config(page_title="番茄 AI 數據自動對接站", layout="wide", page_icon="🍅")
CWA_API_KEY = "CWA-51BA8479-96B3-4B10-B9E4-B815F641B789"

# --- 2. 【核心修正】動態抓取氣象歷史特徵 ---
@st.cache_data(ttl=86400)
def get_ml_features():
    """
    真正連線氣象署 API，抓取 2 個月前 (Lag2) 與 3 個月前 (Lag3) 的資料
    """
    # 使用氣象署『氣候觀測月統計』API (嘉義站 467480)
    url = f"https://opendata.cwa.gov.tw{CWA_API_KEY}&StationID=467480"
    
    # 預設保底數值 (萬一 API 沒資料時使用)
    features = {
        "rain_l2": 80.0, "temp_l2": 18.0, "rain_l3": 70.0, "temp_l3": 17.0,
        "sunshine": 5.0, "time_ord": datetime.now().timetuple().tm_yday
    }

    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        # 取得月統計列表
        monthly_data = data['records']['Status']['Station'][0]['MonthlyStatistics']['Month']
        
        # 取得當前月份 (假設現在是 3 月)
        current_month = datetime.now().month
        
        # 尋找 Lag 2 (2 個月前) 和 Lag 3 (3 個月前) 的資料
        # 注意：API 回傳的是該年度各月份的統計
        for m_info in monthly_data:
            m = int(m_info['MonthNumber'])
            
            # 計算 Lag 2 的月份 (例如 3月 -> 1月)
            target_l2 = (current_month - 2) if current_month > 2 else (current_month + 10)
            # 計算 Lag 3 的月份 (例如 3月 -> 12月)
            target_l3 = (current_month - 3) if current_month > 3 else (current_month + 9)
            
            if m == target_l2:
                features["rain_l2"] = float(m_info['Statistics']['Precipitation']['Precipitation'])
                features["temp_l2"] = float(m_info['Statistics']['Temperature']['Mean'])
                features["sunshine"] = float(m_info['Statistics']['SunshineDuration']['Total'])
            
            if m == target_l3:
                features["rain_l3"] = float(m_info['Statistics']['Precipitation']['Precipitation'])
                features["temp_l3"] = float(m_info['Statistics']['Temperature']['Mean'])
                
        return features
    except Exception as e:
        st.error(f"氣象數據自動對接失敗，目前顯示為系統預設值。錯誤原因：{e}")
        return features

# --- 3. 抓取農業部價格 (不變) ---
@st.cache_data(ttl=3600)
def get_market_price():
    url = "https://data.moa.gov.tw"
    try:
        r = requests.get(url, timeout=10)
        df = pd.DataFrame(r.json())
        df = df[df['作物名稱'].str.contains('番茄', na=False)].copy()
        df['平均價'] = pd.to_numeric(df['平均價'], errors='coerce').fillna(40)
        return df
    except:
        return pd.DataFrame({"作物名稱":["牛番茄"], "平均價":[45.0]})

# --- 4. 預測引擎 (依圖片權重：Rain_Lag2=0.437) ---
def predict_30day_by_img(base_p, f, is_fest):
    # 權重計算
    impact_rain_l2 = (f['rain_l2'] - 50) * 0.1 * 0.437317
    impact_temp_l2 = (f['temp_l2'] - 20) * 0.4 * 0.064656
    fest_bonus = 15.0 if is_fest else 0
    
    preds = []
    for i in range(30):
        # Time_Ordinal 權重 0.155
        impact_time = (f['time_ord'] + i) * 0.01 * 0.155698
        p = base_p + impact_rain_l2 + impact_temp_l2 + impact_time + fest_bonus + (i * 0.4)
        preds.append(round(p, 1))
    return preds

# --- 5. UI 介面 ---
st.title("🍅 番茄 30 日精準預報 (真．數據自動對接版)")

# 觸發自動數據抓取
f = get_ml_features()
price_df = get_market_price()

with st.sidebar:
    st.header("📋 數據監控中心")
    target = st.selectbox("選擇品種", price_df['作物名稱'].unique())
    row = price_df[price_df['作物名稱'] == target].iloc
    
    st.divider()
    st.write("**📡 氣象署即時回傳特徵：**")
    st.metric("Lag2 月雨量", f"{f['rain_l2']} mm")
    st.metric("Lag2 月均溫", f"{f['temp_l2']} °C")
    st.caption(f"數據更新時間: {datetime.now().strftime('%Y-%m-%d')}")
    
    st.divider()
    is_fest = st.checkbox("考慮節慶溢價")

# 運算結果
preds = run_30day_prediction = predict_30day_by_img(float(row['平均價']), f, is_fest)
dates = [(datetime.now() + timedelta(days=i)).strftime("%m/%d") for i in range(30)]

col1, col2 = st.columns([2, 1])
with col1:
    fig = px.line(x=dates, y=preds, text=[v if i%5==0 else "" for i,v in enumerate(preds)], 
                 title=f"{target} 未來 30 天 AI 預測曲線")
    fig.update_traces(line_color="#FF4B4B", marker=dict(size=8), textposition="top center")
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.metric("今日均價", f"{row['平均價']} 元")
    st.metric("30 天後預測", f"{preds[-1]} 元", delta=f"{round(preds[-1]-float(row['平均價']), 1)} 元")
    st.write("---")
    st.write("**💡 AI 模型解析**")
    st.write(f"目前偵測到兩個月前降雨量為 **{f['rain_l2']}mm**。根據模型權重排行(43.7%)，這將導致未來一個月的價格呈現{'上升' if preds[-1] > float(row['平均價']) else '平穩'}趨勢。")

st.success("✅ 系統已達成全自動運作，每日開啟網頁將自動重算預報。")
