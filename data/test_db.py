import sqlite3
import os
import random
from datetime import date, datetime, timedelta

# 数据库文件路径
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'credit_bonus.db')

# 连接数据库
conn = sqlite3.connect(DATABASE_PATH)

cur = conn.cursor()
str = "SELECT COUNT(*) AS high_bonus_count FROM cash_bonus_record WHERE bonus_amount > 20"
cur.execute(str)
for row in cur.fetchall():
    print(row)

conn.close()
