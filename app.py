import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta

# --- 1. 初始化設定 ---
st.set_page_config(page_title="番茄 AI 實時預報系統", layout="wide", page_icon="🍅")

# 你的 API 金鑰
CWA_API_KEY = "CWA-51BA8479-96B3-4B10-B9E4-B815F641B789"

# --- 2. 【即時氣象數據】自動對接氣象署 API ---
@st.cache_data(ttl=86400)
def fetch_realtime_weather():
    """
    根據當前日期，自動抓取 Lag 2 和 Lag 3 的真實觀測值
    """
    # 站碼 467480 (嘉義站) - 番茄重要產區
    url = f"https://opendata.cwa.gov.tw{CWA_API_KEY}&StationID=467480"
    
    # 初始化特徵包 (若 API 異常時的保底參考值)
    features = {"rain_l2": 0.0, "temp_l2": 0.0, "rain_l3": 0.0, "temp_l3": 0.0, "time_ord": datetime.now().timetuple().tm_yday}

    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        # 解析月份列表
        months_list = data['records']['Status']['Station']['MonthlyStatistics']['Month']
        
        curr_m = datetime.now().month
        # 計算滯後月份 (例如 3月 -> Lag2 是 1月, Lag3 是 12月)
        target_l2 = (curr_m - 2) if curr_m > 2 else (curr_m + 10)
        target_l3 = (curr_m - 3) if curr_m > 3 else (curr_m + 9)

        for m_data in months_list:
            m_num = int(m_data['MonthNumber'])
            if m_num == target_l2:
                features["rain_l2"] = float(m_data['Statistics']['Precipitation']['Precipitation'])
                features["temp_l2"] = float(m_data['Statistics']['Temperature']['Mean'])
            elif m_num == target_l3:
                features["rain_l3"] = float(m_data['Statistics']['Precipitation']['Precipitation'])
                features["temp_l3"] = float(m_data['Statistics']['Temperature']['Mean'])
        return features
    except Exception as e:
        st.sidebar.warning(f"氣象 API 連線中或異常: {e}")
        return features

# --- 3. 【即時市場數據】自動對接農業部 API ---
@st.cache_data(ttl=3600)
def fetch_realtime_market():
    """
    抓取今日批發市場最新成交價
    """
    url = "https://data.moa.gov.tw"
    try:
        r = requests.get(url, timeout=10)
        df = pd.DataFrame(r.json())
        # 過濾番茄類
        df = df[df['作物名稱'].str.contains('番茄', na=False)].copy()
        # 轉換數值格式
        df['平均價'] = pd.to_numeric(df['平均價'], errors='coerce')
        df['交易量'] = pd.to_numeric(df['交易量'], errors='coerce')
        return df.dropna(subset=['平均價'])
    except Exception as e:
        st.sidebar.error(f"市場 API 連線異常: {e}")
        return pd.DataFrame({"作物名稱":["無資料"], "平均價":[0], "交易量":[0]})

# --- 4. 【核心引擎】依圖片權重進行 30 天推理 ---
def ai_engine_30d(base_p, f, is_fest):
    # 權重 1: Lag2 雨量 (0.437317) - 以歷史均值 100mm 為基準線
    impact_rain = (f['rain_l2'] - 100) * 0.15 * 0.437317
    # 權重 3: Lag2 氣溫 (0.064656) - 以 20度 為基準線
    impact_temp = (f['temp_l2'] - 20) * 0.5 * 0.064656
    # 節慶因子 (商業預警)
    fest_bonus = 15.0 if is_fest else 0
    
    preds = []
    for i in range(30):
        # 權重 2: Time_Ordinal (0.155698)
        current_ord = f['time_ord'] + i
        impact_time = (current_ord * 0.01) * 0.155698
        
        # 綜合計算：基礎價 + 權重修正項 + 時間趨勢
        price = base_p + impact_rain + impact_temp + impact_time + fest_bonus + (i * 0.4)
        preds.append(round(price, 1))
    return preds

# --- 5. 網頁 UI 呈現 ---
st.title("🍅 番茄 30 日全數據自動預報系統")
st.markdown(f"**目前時間：** {datetime.now().strftime('%Y-%m-%d %H:%M')} | **核心模型：** Top 20 關鍵特徵權重版")

# 獲取實時數據
weather_feat = fetch_realtime_weather()
market_df = fetch_realtime_market()

with st.sidebar:
    st.header("🔍 即時數據監控")
    if not market_df.empty and market_df['作物名稱'].iloc[0] != "無資料":
        target = st.selectbox("請選擇番茄品種", market_df['作物名稱'].unique())
        selected_row = market_df[market_df['作物名稱'] == target].iloc[0]
        base_price = float(selected_row['平均價'])
        st.success(f"已對接今日市場價：{base_price} 元")
    else:
        st.error("無法取得即時市場價格")
        base_price = 45.0

    st.divider()
    st.write("**📡 氣象署實時回傳 (Lag 2)：**")
    st.metric("二個月前累積雨量", f"{weather_feat['rain_l2']} mm")
    st.metric("二個月前平均氣溫", f"{weather_feat['temp_l2']} °C")
    
    st.divider()
    is_festival = st.checkbox("考慮節慶溢價因素")

# 運算並繪圖
if base_price > 0:
    predictions = ai_engine_30d(base_price, weather_feat, is_festival)
    dates = [(datetime.now() + timedelta(days=i)).strftime("%m/%d") for i in range(30)]

    col1, col2 = st.columns([2, 1])
    
    with col1:
        fig = px.line(x=dates, y=predictions, text=[v if i%5==0 else "" for i,v in enumerate(predictions)],
                     title=f"{target} 未來一個月預測走勢", labels={'x':'日期', 'y':'預估價格 (元/kg)'})
        fig.update_traces(line_color="#E74C3C", marker=dict(size=8), textposition="top center")
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.metric("今日實時均價", f"{base_price} 元")
        st.metric("30 天後 AI 預測", f"{predictions[-1]} 元", delta=f"{round(predictions[-1]-base_price, 1)} 元")
        
        st.divider()
        st.write("### 🧠 模型權重分析")
        st.write(f"- **最大影響因子**：二個月前雨量 ({weather_feat['rain_l2']}mm)，權重 43.7%")
        st.write(f"- **年度季節趨勢**：年度序數 ({weather_feat['time_ord']})，權重 15.5%")
        
        if predictions[-1] > base_price * 1.15:
            st.warning("⚠️ 預警：受滯後氣候影響，一個月後價格看漲。")
        else:
            st.info("✅ 資訊：目前氣候因子對價格影響平穩。")

st.caption("數據自動對接來源：中華民國農業部、中央氣象署開放資料平臺")
