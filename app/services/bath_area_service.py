from app.repositories import BathAreaRepository, WristbandRepository


class BathAreaService:

    @staticmethod
    def list_all():
        return BathAreaRepository.list_all()

    @staticmethod
    def list_active():
        return BathAreaRepository.list_active()

    @staticmethod
    def create(name, description='', base_price=0.0, deposit_amount=0.0):
        return BathAreaRepository.create(name, description, base_price, deposit_amount)

    @staticmethod
    def update(area_id, name, description='', base_price=0.0, deposit_amount=0.0, is_active=True):
        return BathAreaRepository.update(
            area_id,
            name=name,
            description=description,
            base_price=float(base_price),
            deposit_amount=float(deposit_amount),
            is_active=is_active
        )

    @staticmethod
    def delete(area_id):
        has_bands = BathAreaRepository.has_bands(area_id)
        if has_bands:
            raise ValueError('该浴区下还有手牌，无法删除')
        return BathAreaRepository.delete(area_id)

    @staticmethod
    def get_by_id(area_id):
        return BathAreaRepository.get_by_id(area_id)
