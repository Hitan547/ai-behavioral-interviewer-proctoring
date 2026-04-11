import sqlite3

conn = sqlite3.connect('data/psysense.db')
cur  = conn.cursor()

# Check current state
cur.execute("SELECT username, email FROM users WHERE role='recruiter'")
print("Before:", cur.fetchall())

# Set recruiter email
conn.execute("UPDATE users SET email='hitank2004@gmail.com' WHERE username='recruiter'")
conn.commit()

# Verify
cur.execute("SELECT username, email FROM users WHERE role='recruiter'")
print("After:", cur.fetchall())

conn.close()
print("Done")