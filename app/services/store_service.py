from datetime import date
from app.repositories import StoreRepository, ClearingRuleRepository


class StoreService:

    @staticmethod
    def list_stores():
        return StoreRepository.list_all()

    @staticmethod
    def create_store(data):
        store_code = data.get('store_code', '').strip()
        if not store_code:
            raise ValueError('门店编码不能为空')
        name = data.get('name', '').strip()
        if not name:
            raise ValueError('门店名称不能为空')

        existing = StoreRepository.get_by_store_code(store_code)
        if existing:
            raise ValueError('门店编码已存在')

        StoreRepository.create(
            store_code=store_code,
            name=name,
            address=data.get('address', ''),
            contact_phone=data.get('contact_phone', ''),
            manager_name=data.get('manager_name', ''),
            is_headquarters=data.get('is_headquarters', False),
        )

    @staticmethod
    def update_store(store_id, data):
        store = StoreRepository.get_by_id(store_id)
        if not store:
            raise ValueError('门店不存在')

        store_code = data.get('store_code')
        if store_code and store_code != store['store_code']:
            existing = StoreRepository.get_by_store_code(store_code)
            if existing:
                raise ValueError('门店编码已存在')

        update_data = {
            'store_code': store_code if store_code else store['store_code'],
            'name': data.get('name', store['name']),
            'address': data.get('address', store.get('address', '')),
            'contact_phone': data.get('contact_phone', store.get('contact_phone', '')),
            'manager_name': data.get('manager_name', store.get('manager_name', '')),
            'is_active': data.get('is_active', store.get('is_active', True)),
            'is_headquarters': data.get('is_headquarters', store.get('is_headquarters', False)),
        }

        StoreRepository.update(store_id, **update_data)

    @staticmethod
    def delete_store(store_id):
        store = StoreRepository.get_by_id(store_id)
        if not store:
            raise ValueError('门店不存在')

        if store.get('is_headquarters'):
            raise ValueError('总部门店不可删除')

        related_counts = StoreRepository.get_related_data_count(store_id)
        related_names = {
            'bath_areas': '浴区',
            'wristbands': '手牌',
            'users': '用户',
            'issue_records': '发放记录',
            'shift_records': '班次记录',
            'members': '会员',
            'cross_store_records': '跨店记录',
            'clearing_records': '清分记录',
            'clearing_rules': '清分规则',
        }

        has_related = []
        for key, name in related_names.items():
            if related_counts.get(key, 0) > 0:
                has_related.append(f'{name}({related_counts[key]}条)')

        if has_related:
            raise ValueError(f'该门店下存在关联数据：{", ".join(has_related)}，无法删除')

        StoreRepository.delete(store_id)

    @staticmethod
    def get_store_stats(store_id):
        store = StoreRepository.get_by_id(store_id)
        if not store:
            raise ValueError('门店不存在')

        today = date.today()
        today_str = today.strftime('%Y-%m-%d')
        return StoreRepository.get_stats(store_id, today_str)


class ClearingRuleService:

    @staticmethod
    def list_clearing_rules():
        return ClearingRuleRepository.list_all()

    @staticmethod
    def create_clearing_rule(data):
        name = data.get('name', '').strip()
        if not name:
            raise ValueError('规则名称不能为空')
        rule_type = data.get('rule_type', '').strip()
        if not rule_type:
            raise ValueError('规则类型不能为空')
        if not data.get('source_store_id'):
            raise ValueError('源门店不能为空')

        level_ids = data.get('applicable_level_ids', [])
        if isinstance(level_ids, str):
            level_ids = [int(x) for x in level_ids.split(',') if x.strip()]

        target_store_id = data.get('target_store_id') or None

        source_ratio = float(data.get('source_ratio', 50))
        target_ratio = float(data.get('target_ratio', 50))
        hq_subsidy_ratio = float(data.get('hq_subsidy_ratio', 0))

        if source_ratio + target_ratio + hq_subsidy_ratio != 100:
            raise ValueError('源门店分成比例 + 目标门店分成比例 + 总部补贴比例 必须等于 100')

        ClearingRuleRepository.create(
            name=name,
            rule_type=rule_type,
            source_store_id=data['source_store_id'],
            target_store_id=target_store_id,
            source_ratio=source_ratio,
            target_ratio=target_ratio,
            hq_subsidy_ratio=hq_subsidy_ratio,
            hq_subsidy_max=float(data.get('hq_subsidy_max', 0)),
            applicable_level_ids=level_ids,
            priority=int(data.get('priority', 0)),
            description=data.get('description', ''),
        )

    @staticmethod
    def update_clearing_rule(rule_id, data):
        rule = ClearingRuleRepository.get_by_id(rule_id)
        if not rule:
            raise ValueError('清分规则不存在')

        level_ids = data.get('applicable_level_ids', rule.get('applicable_level_ids', []))
        if isinstance(level_ids, str):
            level_ids = [int(x) for x in level_ids.split(',') if x.strip()]

        target_store_id = data.get('target_store_id')
        if target_store_id is not None:
            target_store_id = target_store_id or None

        source_ratio = float(data.get('source_ratio', rule.get('source_ratio', 50)))
        target_ratio = float(data.get('target_ratio', rule.get('target_ratio', 50)))
        hq_subsidy_ratio = float(data.get('hq_subsidy_ratio', rule.get('hq_subsidy_ratio', 0)))

        if source_ratio + target_ratio + hq_subsidy_ratio != 100:
            raise ValueError('源门店分成比例 + 目标门店分成比例 + 总部补贴比例 必须等于 100')

        update_data = {
            'name': data.get('name', rule['name']),
            'rule_type': data.get('rule_type', rule['rule_type']),
            'source_store_id': data.get('source_store_id', rule['source_store_id']),
            'target_store_id': target_store_id if target_store_id is not None else rule.get('target_store_id'),
            'source_ratio': source_ratio,
            'target_ratio': target_ratio,
            'hq_subsidy_ratio': hq_subsidy_ratio,
            'hq_subsidy_max': float(data.get('hq_subsidy_max', rule.get('hq_subsidy_max', 0))),
            'applicable_level_ids': level_ids,
            'priority': int(data.get('priority', rule.get('priority', 0))),
            'description': data.get('description', rule.get('description', '')),
            'is_active': data.get('is_active', rule.get('is_active', True)),
        }

        ClearingRuleRepository.update(rule_id, **update_data)

    @staticmethod
    def delete_clearing_rule(rule_id):
        rule = ClearingRuleRepository.get_by_id(rule_id)
        if not rule:
            raise ValueError('清分规则不存在')
        ClearingRuleRepository.delete(rule_id)


def list_stores():
    return StoreService.list_stores()


def create_store(data):
    return StoreService.create_store(data)


def update_store(store_id, data):
    return StoreService.update_store(store_id, data)


def delete_store(store_id):
    return StoreService.delete_store(store_id)


def get_store_stats(store_id):
    return StoreService.get_store_stats(store_id)


def list_clearing_rules():
    return ClearingRuleService.list_clearing_rules()


def create_clearing_rule(data):
    return ClearingRuleService.create_clearing_rule(data)


def update_clearing_rule(rule_id, data):
    return ClearingRuleService.update_clearing_rule(rule_id, data)


def delete_clearing_rule(rule_id):
    return ClearingRuleService.delete_clearing_rule(rule_id)
