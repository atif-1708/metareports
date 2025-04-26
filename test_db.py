import psycopg2

conn = psycopg2.connect(
    dbname="flask_reports",
    user="reportuser",
    password="admin",
    host="localhost"
)
cur = conn.cursor()

# Test query (replace 'reports' with your actual table name)
cur.execute("SELECT * FROM users LIMIT 1")
print(cur.fetchone())

cur.close()
conn.close()