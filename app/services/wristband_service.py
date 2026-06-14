from datetime import datetime
from app.repositories import (
    WristbandRepository,
    IssueRecordRepository,
    StatusLogRepository,
    BathAreaRepository,
)


class WristbandService:

    @staticmethod
    def list_wristbands(status='', area_id=''):
        return WristbandRepository.list(status=status, area_id=area_id)

    @staticmethod
    def create_wristband(wristband_no, bath_area_id, operator_id):
        exists = WristbandRepository.get_by_wristband_no(wristband_no)
        if exists:
            raise ValueError('手牌编号已存在')

        WristbandRepository.create(wristband_no, bath_area_id)

        new_band = WristbandRepository.get_by_wristband_no(wristband_no)
        if new_band:
            remark = f'初始浴区ID: {bath_area_id}' if bath_area_id else '未指定浴区'
            StatusLogRepository.create(
                wristband_id=new_band['id'],
                old_status=None,
                new_status='available',
                change_reason='手牌创建',
                operator_id=operator_id,
                remark=remark,
            )
        return new_band

    @staticmethod
    def update_wristband(band_id, bath_area_id, operator_id):
        band = WristbandRepository.get_by_id(band_id)
        if not band:
            raise ValueError('手牌不存在')

        old_area_id = band['bath_area_id']
        new_area_id = bath_area_id

        old_area = BathAreaRepository.get_by_id(old_area_id) if old_area_id else None
        new_area = BathAreaRepository.get_by_id(new_area_id) if new_area_id else None

        WristbandRepository.update_bath_area(band_id, new_area_id)

        area_changed = (old_area_id or None) != (new_area_id or None)
        if area_changed:
            old_area_name = old_area['name'] if old_area else '无'
            new_area_name = new_area['name'] if new_area else '无'
            StatusLogRepository.create(
                wristband_id=band_id,
                old_status=band['current_status'],
                new_status=band['current_status'],
                change_reason='浴区变更',
                operator_id=operator_id,
                remark=f'从 {old_area_name} 调整为 {new_area_name}',
            )
        return True

    @staticmethod
    def delete_wristband(band_id, operator_id):
        band = WristbandRepository.get_by_id(band_id)
        if not band:
            raise ValueError('手牌不存在')
        if band['current_status'] == 'issued':
            raise ValueError('手牌已发放，无法删除')

        StatusLogRepository.create(
            wristband_id=band_id,
            old_status=band['current_status'],
            new_status=None,
            change_reason='手牌删除',
            operator_id=operator_id,
            remark=f'手牌编号: {band["wristband_no"]}',
        )
        WristbandRepository.delete(band_id)
        return True

    @staticmethod
    def get_available_bands(area_id=''):
        return WristbandRepository.list_available(area_id=area_id)

    @staticmethod
    def log_status_change(wristband_id, new_status, change_reason, **kwargs):
        old_status = kwargs.get('old_status')
        issue_record_id = kwargs.get('issue_record_id')
        operator_id = kwargs.get('operator_id')
        phone = kwargs.get('phone')
        customer_name = kwargs.get('customer_name')
        remark = kwargs.get('remark')
        change_time = kwargs.get('change_time')

        StatusLogRepository.create(
            wristband_id=wristband_id,
            new_status=new_status,
            change_reason=change_reason,
            old_status=old_status,
            issue_record_id=issue_record_id,
            operator_id=operator_id,
            phone=phone,
            customer_name=customer_name,
            remark=remark,
            change_time=change_time,
        )

    @staticmethod
    def get_wristband_status_log(band_id):
        band = WristbandRepository.get_by_id(band_id)
        logs = StatusLogRepository.get_by_wristband(band_id)
        return {
            'wristband': band,
            'logs': logs,
        }

    @staticmethod
    def get_issue_record_status_log(record_id):
        return StatusLogRepository.get_by_issue_record(record_id)

    @staticmethod
    def phone_has_unsettled_loss(phone):
        return IssueRecordRepository.count_by_phone_with_unsettled_loss(phone)
