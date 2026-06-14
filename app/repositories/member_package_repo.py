from app.database import query, query_one, execute, execute_and_return_id
from .base import BaseRepository


class MemberPackageRepository(BaseRepository):
    table_name = 'member_packages'

    @classmethod
    def list_all(cls):
        sql = 'SELECT * FROM member_packages ORDER BY id DESC'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def list_active(cls):
        sql = 'SELECT * FROM member_packages WHERE is_active = TRUE ORDER BY id'
        results = query(sql)
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_by_id(cls, pkg_id):
        return super().get_by_id(pkg_id)

    @classmethod
    def get_active_by_id(cls, pkg_id):
        sql = 'SELECT * FROM member_packages WHERE id = %s AND is_active = TRUE'
        result = query_one(sql, (pkg_id,))
        return dict(result) if result else None

    @classmethod
    def create(cls, name, package_type, total_count, valid_days, price, original_value,
               applicable_bath_area_ids=None, cross_store_enabled=False, description=''):
        sql = '''
            INSERT INTO member_packages (name, package_type, total_count, valid_days, price,
                                       original_value, applicable_bath_area_ids,
                                       cross_store_enabled, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        '''
        return execute(sql, (name, package_type, total_count, valid_days,
                          float(price), float(original_value),
                          applicable_bath_area_ids or [], cross_store_enabled, description))

    @classmethod
    def update(cls, pkg_id, **kwargs):
        return super().update(pkg_id, **kwargs)

    @classmethod
    def delete(cls, pkg_id):
        return super().delete(pkg_id)


class MemberPackagePurchaseRepository(BaseRepository):
    table_name = 'member_package_purchases'

    @classmethod
    def get_by_member(cls, member_id):
        sql = '''
            SELECT mpp.*, mp.name as package_name, mp.package_type, mp.original_value
            FROM member_package_purchases mpp
            LEFT JOIN member_packages mp ON mpp.package_id = mp.id
            WHERE mpp.member_id = %s
            ORDER BY mpp.created_at DESC
        '''
        results = query(sql, (member_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def get_available_packages(cls, member_id, bath_area_id=None):
        from datetime import datetime
        now = datetime.now()
        sql = '''
            SELECT mpp.*, mp.name as package_name, mp.package_type, mp.original_value
            FROM member_package_purchases mpp
            LEFT JOIN member_packages mp ON mpp.package_id = mp.id
            WHERE mpp.member_id = %s AND mpp.status = 'active'
              AND (mpp.expire_at IS NULL OR mpp.expire_at > %s)
              AND (mpp.remaining_count IS NULL OR mpp.remaining_count > 0)
            ORDER BY mpp.activated_at DESC
        '''
        purchases = query(sql, (member_id, now))
        result = []
        for p in purchases:
            p = dict(p)
            if bath_area_id and p.get('applicable_bath_area_ids'):
                if bath_area_id not in (p['applicable_bath_area_ids'] or []):
                    continue
            result.append(p)
        return result

    @classmethod
    def get_by_id(cls, purchase_id):
        sql = 'SELECT * FROM member_package_purchases WHERE id = %s'
        result = query_one(sql, (purchase_id,))
        return dict(result) if result else None

    @classmethod
    def create(cls, member_id, package_id, purchase_price, remaining_count, total_count, expire_at):
        sql = '''
            INSERT INTO member_package_purchases (member_id, package_id, purchase_price,
                                                remaining_count, total_count, expire_at)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        '''
        from db import execute_and_return_id
        return execute_and_return_id(sql, (member_id, package_id, float(purchase_price),
                                         remaining_count, total_count, expire_at))

    @classmethod
    def get_latest_by_member_and_package(cls, member_id, package_id):
        sql = '''
            SELECT id FROM member_package_purchases
            WHERE member_id = %s AND package_id = %s
            ORDER BY created_at DESC LIMIT 1
        '''
        result = query_one(sql, (member_id, package_id))
        return dict(result) if result else None

    @classmethod
    def decrement_remaining(cls, purchase_id):
        sql = '''
            UPDATE member_package_purchases SET remaining_count = remaining_count - 1
            WHERE id = %s
        '''
        return execute(sql, (purchase_id,))

    @classmethod
    def mark_used_up(cls, purchase_id):
        sql = "UPDATE member_package_purchases SET status = 'used_up' WHERE id = %s"
        return execute(sql, (purchase_id,))


class MemberPackageUsageRepository(BaseRepository):
    table_name = 'member_package_usages'

    @classmethod
    def get_by_member(cls, member_id):
        sql = '''
            SELECT mpu.*, mp.name as package_name
            FROM member_package_usages mpu
            LEFT JOIN member_package_purchases mpp ON mpu.purchase_id = mpp.id
            LEFT JOIN member_packages mp ON mpp.package_id = mp.id
            WHERE mpu.member_id = %s
            ORDER BY mpu.used_at DESC
        '''
        results = query(sql, (member_id,))
        return [dict(r) for r in results] if results else []

    @classmethod
    def count_by_date(cls, date_str):
        sql = "SELECT COUNT(*) as cnt FROM member_package_usages WHERE DATE(used_at) = %s"
        result = query_one(sql, (date_str,))
        return int(result['cnt']) if result else 0

    @classmethod
    def create(cls, purchase_id, member_id, issue_record_id, deduction_amount):
        sql = '''
            INSERT INTO member_package_usages (purchase_id, member_id, issue_record_id, deduction_amount)
            VALUES (%s, %s, %s, %s)
        '''
        return execute(sql, (purchase_id, member_id, issue_record_id, float(deduction_amount)))
