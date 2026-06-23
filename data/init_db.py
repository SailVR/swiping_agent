"""初始化信用卡刷卡金数据分析数据库

创建用户、信用卡交易、刷卡金发放、刷卡金使用、活动配置表，并插入模拟测试数据。
适配 SQLite3，自动生成批量测试数据，支持重复运行重置数据。
"""
import sqlite3
import os
import random
from datetime import date, datetime, timedelta

# 数据库文件路径
DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'credit_bonus.db')

# 全局模拟数据配置
PHONE_PREFIX = "138"
DOMAIN_SUFFIX = "@credit-bank.com"
MERCHANT_TYPES = ["餐饮", "商超", "加油", "酒店", "出行", "娱乐", "百货", "医疗"]
BONUS_TYPE_MAP = {1: "交易返现", 2: "活动赠送", 3: "积分兑换"}
TRANS_TYPE_MAP = {1: "正常消费", 2: "退款"}


def create_tables(conn):
    """创建刷卡金分析系统数据表 + 索引 + 外键约束"""
    cursor = conn.cursor()

    # 1. 用户信息表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_info (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL UNIQUE,
        user_name TEXT,
        card_no TEXT NOT NULL,
        register_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_level INTEGER DEFAULT 1,
        status INTEGER DEFAULT 1,
        remark TEXT
    )
    ''')

    # 2. 信用卡交易流水表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS card_transaction (
        trans_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        card_no TEXT NOT NULL,
        trans_time TIMESTAMP NOT NULL,
        trans_amount DECIMAL(10, 2) NOT NULL,
        merchant_name TEXT,
        merchant_type TEXT,
        trans_type INTEGER DEFAULT 1,
        status INTEGER DEFAULT 1,
        FOREIGN KEY (user_id) REFERENCES user_info(user_id)
    )
    ''')

    # 3. 刷卡金发放记录表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cash_bonus_record (
        bonus_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        trans_id INTEGER,
        bonus_amount DECIMAL(10, 2) NOT NULL,
        bonus_type INTEGER NOT NULL,
        send_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expire_time TIMESTAMP,
        is_used INTEGER DEFAULT 0,
        activity_id INTEGER,
        FOREIGN KEY (user_id) REFERENCES user_info(user_id),
        FOREIGN KEY (trans_id) REFERENCES card_transaction(trans_id)
    )
    ''')

    # 4. 刷卡金使用抵扣表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cash_bonus_usage (
        usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
        bonus_id INTEGER NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        use_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        deduct_amount DECIMAL(10, 2) NOT NULL,
        deduct_trans_id INTEGER,
        usage_desc TEXT,
        FOREIGN KEY (bonus_id) REFERENCES cash_bonus_record(bonus_id),
        FOREIGN KEY (user_id) REFERENCES user_info(user_id),
        FOREIGN KEY (deduct_trans_id) REFERENCES card_transaction(trans_id)
    )
    ''')

    # 5. 活动配置表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS activity_config (
        activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
        activity_name TEXT NOT NULL,
        activity_rule TEXT,
        start_time TIMESTAMP NOT NULL,
        end_time TIMESTAMP NOT NULL,
        total_budget DECIMAL(12, 2) DEFAULT 0,
        status INTEGER DEFAULT 1,
        create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # 创建索引，提升数据分析查询效率
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_card ON user_info(card_no)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_phone ON user_info(phone)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trans_user ON card_transaction(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trans_time ON card_transaction(trans_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_trans_merchant ON card_transaction(merchant_type)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bonus_user ON cash_bonus_record(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bonus_expire ON cash_bonus_record(expire_time)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_bonus_used ON cash_bonus_record(is_used)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_user ON cash_bonus_usage(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_time ON cash_bonus_usage(use_time)')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_config(start_time, end_time)')

    # 开启 SQLite 外键约束
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    print("✅ 数据表与索引创建完成")


def insert_sample_data(conn):
    """批量插入模拟测试数据：活动、用户、交易、刷卡金、使用记录"""
    cursor = conn.cursor()

    # 清空原有数据 + 重置自增ID（重复运行可重置数据）
    tables = ["cash_bonus_usage", "cash_bonus_record", "card_transaction", "user_info", "activity_config"]
    for tbl in tables:
        cursor.execute(f"DELETE FROM {tbl}")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN (?, ?, ?, ?, ?)", tables)
    conn.commit()
    print("✅ 旧数据清空，自增ID已重置")

    # ---------------------- 1. 插入活动配置数据 ----------------------
    activity_list = [
        ("日常消费返现活动", "单笔消费满100元返现3元，单日上限30元", "2025-01-01 00:00:00", "2025-12-31 23:59:59", 500000.00, 1),
        ("周末加倍返现", "周六周日返现比例翻倍", "2025-01-01 00:00:00", "2025-12-31 23:59:59", 200000.00, 1),
        ("新用户专属福利", "新绑卡用户首笔交易赠10元刷卡金", "2025-03-01 00:00:00", "2025-11-30 23:59:59", 150000.00, 1),
        ("加油专属活动", "加油类交易额外返现", "2025-02-01 00:00:00", "2025-10-31 23:59:59", 100000.00, 1),
        ("积分兑换刷卡金", "100积分兑换1元刷卡金", "2025-01-01 00:00:00", "2025-12-31 23:59:59", 80000.00, 1)
    ]
    cursor.executemany('''
        INSERT INTO activity_config (activity_name, activity_rule, start_time, end_time, total_budget, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', activity_list)
    conn.commit()

    # 获取活动ID映射
    cursor.execute("SELECT activity_id, activity_name FROM activity_config")
    activity_map = {name: aid for aid, name in cursor.fetchall()}
    print(f"✅ 插入 {len(activity_list)} 条活动数据")

    # ---------------------- 2. 批量生成用户数据 ----------------------
    user_count = 80  # 模拟80个信用卡用户
    user_list = []
    name_pool = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙"]
    name_suffix = ["伟", "芳", "强", "娜", "敏", "静", "涛", "丽", "军", "鹏"]

    for idx in range(1, user_count + 1):
        # 随机姓名
        user_name = random.choice(name_pool) + random.choice(name_suffix)
        # 随机手机号
        phone = f"{PHONE_PREFIX}{random.randint(10000000, 99999999)}"
        # 模拟信用卡卡号
        card_no = f"6226{random.randint(1000000000000000, 9999999999999999)}"
        # 注册时间：近1年内随机时间
        reg_days = random.randint(0, 365)
        reg_time = (datetime.now() - timedelta(days=reg_days)).strftime("%Y-%m-%d %H:%M:%S")
        # 用户等级 1普通 2VIP 3高端
        user_level = random.choices([1, 2, 3], weights=[0.7, 0.2, 0.1])[0]
        status = 1

        user_list.append((phone, user_name, card_no, reg_time, user_level, status))

    cursor.executemany('''
        INSERT INTO user_info (phone, user_name, card_no, register_time, user_level, status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', user_list)
    conn.commit()

    # 获取用户ID映射
    cursor.execute("SELECT user_id, phone FROM user_info")
    user_map = {phone: uid for uid, phone in cursor.fetchall()}
    print(f"✅ 插入 {user_count} 条用户数据")

    # ---------------------- 3. 批量生成交易流水数据 ----------------------
    trans_list = []
    merchant_names = ["永辉超市", "中石化加油站", "海底捞", "美团外卖", "滴滴出行", "如家酒店", "万达影院", "社区门诊"]
    total_trans = 0

    for phone, user_id in user_map.items():
        # 每个用户生成 3~15 笔交易
        trans_num = random.randint(3, 15)
        for _ in range(trans_num):
            card_no = f"6226{random.randint(1000000000000000, 9999999999999999)}"
            # 交易时间：近90天随机
            trans_days = random.randint(0, 90)
            trans_time = (datetime.now() - timedelta(days=trans_days, hours=random.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")
            # 交易金额 10 ~ 5000 元
            trans_amount = round(random.uniform(10.0, 5000.0), 2)
            merchant_name = random.choice(merchant_names)
            merchant_type = random.choice(MERCHANT_TYPES)
            trans_type = random.choices([1, 2], weights=[0.95, 0.05])[0]  # 95%消费 5%退款
            status = 1

            trans_list.append((user_id, card_no, trans_time, trans_amount, merchant_name, merchant_type, trans_type, status))
        total_trans += trans_num

    cursor.executemany('''
        INSERT INTO card_transaction (user_id, card_no, trans_time, trans_amount, merchant_name, merchant_type, trans_type, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', trans_list)
    conn.commit()

    # 获取交易ID映射
    cursor.execute("SELECT trans_id, user_id FROM card_transaction")
    trans_map = cursor.fetchall()
    print(f"✅ 插入 {total_trans} 条交易流水数据")

    # ---------------------- 4. 批量生成刷卡金发放记录 ----------------------
    bonus_list = []
    used_bonus_list = []  # 已使用的刷卡金，用于生成使用记录
    total_bonus = 0

    for trans_id, user_id in trans_map:
        # 仅消费交易才产生刷卡金
        cursor.execute("SELECT trans_type FROM card_transaction WHERE trans_id = ?", (trans_id,))
        t_type = cursor.fetchone()[0]
        if t_type == 2:
            continue

        # 每笔消费随机产生刷卡金（70%概率返现）
        if random.random() > 0.3:
            bonus_type = random.choice([1, 2, 3])
            # 刷卡金金额 1 ~ 30 元
            bonus_amount = round(random.uniform(1.0, 30.0), 2)
            send_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # 有效期 30~90天
            expire_days = random.randint(30, 90)
            expire_time = (datetime.now() + timedelta(days=expire_days)).strftime("%Y-%m-%d %H:%M:%S")
            # 是否已使用：50%概率已核销
            is_used = random.choice([0, 1])
            # 关联活动ID
            activity_id = random.choice(list(activity_map.values()))

            bonus_list.append((user_id, trans_id, bonus_amount, bonus_type, send_time, expire_time, is_used, activity_id))
            total_bonus += 1

    cursor.executemany('''
        INSERT INTO cash_bonus_record (user_id, trans_id, bonus_amount, bonus_type, send_time, expire_time, is_used, activity_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', bonus_list)
    conn.commit()

    # 获取已使用的刷卡金ID
    cursor.execute("SELECT bonus_id, user_id FROM cash_bonus_record WHERE is_used = 1")
    used_bonus_data = cursor.fetchall()
    print(f"✅ 插入 {total_bonus} 条刷卡金发放数据")

    # ---------------------- 5. 批量生成刷卡金使用记录 ----------------------
    usage_list = []
    usage_desc_list = ["账单抵扣", "消费直接抵扣", "分期手续费抵扣"]
    for bonus_id, user_id in used_bonus_data:
        use_time = (datetime.now() - timedelta(days=random.randint(1, 30))).strftime("%Y-%m-%d %H:%M:%S")
        # 抵扣金额 = 刷卡金全额
        cursor.execute("SELECT bonus_amount FROM cash_bonus_record WHERE bonus_id = ?", (bonus_id,))
        deduct_amount = cursor.fetchone()[0]
        # 关联一笔随机交易
        deduct_trans_id = random.choice(trans_map)[0]
        usage_desc = random.choice(usage_desc_list)

        usage_list.append((bonus_id, user_id, use_time, deduct_amount, deduct_trans_id, usage_desc))

    cursor.executemany('''
        INSERT INTO cash_bonus_usage (bonus_id, user_id, use_time, deduct_amount, deduct_trans_id, usage_desc)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', usage_list)
    conn.commit()
    print(f"✅ 插入 {len(usage_list)} 条刷卡金使用记录")


def main():
    """主入口：初始化数据库全流程"""
    # 连接数据库
    conn = sqlite3.connect(DATABASE_PATH)

    # 建表 & 插入测试数据
    create_tables(conn)
    insert_sample_data(conn)

    # cur = conn.cursor()
    # cur.execute("SELECT * FROM user_info LIMIT 10")
    # for row in cur.fetchall():
    #     print(row)

    # 数据库优化整理
    conn.execute("VACUUM")
    conn.close()

    print("\n======================================")
    print(f"🎉 信用卡刷卡金数据分析数据库初始化完成！")
    print(f"📁 数据库文件路径：{DATABASE_PATH}")
    print("======================================")


if __name__ == '__main__':
    main()