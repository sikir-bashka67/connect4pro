from rest_framework.exceptions import APIException


class PaymentRequired(APIException):
    """HTTP 402: действие доступно после оплаты. В ответе можно передать подсказки (цена, что купить)."""
    status_code = 402
    default_detail = 'Требуется оплата.'
    default_code = 'payment_required'

    def __init__(self, detail=None, **extra):
        payload = {'detail': detail or self.default_detail}
        payload.update({k: str(v) for k, v in extra.items()})
        super().__init__(payload)
