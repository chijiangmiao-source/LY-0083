from db import query_one

print('user=', query_one("SELECT id, username FROM users WHERE username = %s", ('admin',)))
print('shift=', query_one("SELECT * FROM shift_records LIMIT 1"))
