from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_stockitem_out_time_stockitem_sold_price_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transaction",
            name="account_delta",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="账户变动额"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="contact_delta",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="往来变动额"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="is_voided",
            field=models.BooleanField(default=False, verbose_name="是否作废"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="作废时间"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="void_reason",
            field=models.CharField(blank=True, max_length=200, verbose_name="作废原因"),
        ),
        migrations.AddField(
            model_name="transaction",
            name="corrected_from",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="corrections", to="core.transaction", verbose_name="更正来源"),
        ),
    ]
