from django.test import SimpleTestCase

from core.models import CapitalAccount, Transaction
from core.serializers import TransactionSerializer


class TransactionSerializerTests(SimpleTestCase):
    def test_capital_account_name_uses_account_field(self):
        account = CapitalAccount(name='主账户')
        tx = Transaction(type='SALE', amount=100, account=account)

        data = TransactionSerializer(tx).data

        self.assertEqual(data['capital_account_name'], '主账户')

    def test_status_display_reflects_void_state(self):
        scenarios = [
            (False, '有效'),
            (True, '作废'),
        ]

        for is_voided, expected in scenarios:
            with self.subTest(is_voided=is_voided):
                tx = Transaction(type='SALE', amount=1, is_voided=is_voided)
                self.assertEqual(TransactionSerializer(tx).data['status_display'], expected)
