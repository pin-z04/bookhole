import sqlite3
import os

def initialize_database():
    # 定義資料庫檔案名稱
    db_filename = 'bookhole.db'
    sql_filename = 'schema.sql'
    
    if not os.path.exists(sql_filename):
        print(f"【錯誤】找不到 {sql_filename} 檔案，請確保它跟此 Python 程式在同一個資料夾。")
        return

    # 連接到 SQLite 資料庫（若檔案不存在會自動建立）
    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()
    
    # 讀取 schema.sql 內的所有 SQL 指令
    with open(sql_filename, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    try:
        # 執行 SQL 腳本來建立所有的資料表
        cursor.executescript(sql_script)
        conn.commit()
        print(f"【成功】資料庫「{db_filename}」已成功建立，且所有資料表已規劃完成！")
    except sqlite3.Error as e:
        print(f"【錯誤】建立資料表時發生問題：{e}")
    finally:
        # 關閉資料庫連線
        conn.close()

if __name__ == '__main__':
    initialize_database()