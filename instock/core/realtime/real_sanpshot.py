import easyquotation
from datetime import datetime, timedelta

def get_real_time_quote(code) -> float:
    quotation = easyquotation.use('sina')
    # 返回数据
    #{'000001':
    # {'name': '平安银行', 'open': 11.56, 'close': 11.56, 'now': 11.62, 'high': 11.66, 'low': 11.53, 'buy': 11.62
    # , 'sell': 11.63, 'turnover': 52080827, 'volume': 604056615.23, 'bid1_volume': 44200, 'bid1': 11.62
    # , 'bid2_volume': 173500, 'bid2': 11.61, 'bid3_volume': 164000, 'bid3': 11.6, 'bid4_volume': 206900
    # , 'bid4': 11.59, 'bid5_volume': 1478900, 'bid5': 11.58, 'ask1_volume': 47000, 'ask1': 11.63
    # , 'ask2_volume': 393300, 'ask2': 11.64, 'ask3_volume': 866600, 'ask3': 11.65, 'ask4_volume': 959700, 'ask4': 11.66
    # , 'ask5_volume': 698400, 'ask5': 11.67, 'date': '2024-12-16', 'time': '13:11:57'}}

    data_res = quotation.real(code)
    data = data_res.get(code)
    if data is None or 'date' not in data or 'time' not in data:
        return None


    current_time = datetime.now()
    data_time = datetime.strptime(f"{data['date']} {data['time']}", "%Y-%m-%d %H:%M:%S")
    # 超过5分钟没有更新数据
    if current_time - data_time > timedelta(minutes=5):
        return None
    return data.get('now')

if __name__ == '__main__':
    print(get_real_time_quote('000001'))