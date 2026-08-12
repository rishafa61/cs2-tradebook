import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_inventoryitem_estimated_price_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='p2ptrade',
            name='given_item',
        ),
        migrations.RemoveField(
            model_name='p2ptrade',
            name='given_skin_name',
        ),
        migrations.RemoveField(
            model_name='p2ptrade',
            name='given_value',
        ),
        migrations.RemoveField(
            model_name='p2ptrade',
            name='received_skin_name',
        ),
        migrations.RemoveField(
            model_name='p2ptrade',
            name='received_value',
        ),
        migrations.RemoveField(
            model_name='p2ptrade',
            name='received_item',
        ),
        migrations.CreateModel(
            name='P2PGivenItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('skin_name', models.CharField(blank=True, max_length=200)),
                ('value', models.DecimalField(decimal_places=2, help_text='Agreed value of this skin (for P&L tracking).', max_digits=12)),
                ('inventory_item', models.ForeignKey(blank=True, help_text='Skin from your inventory that you gave up.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='p2p_given_lines', to='core.inventoryitem')),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='given_lines', to='core.p2ptrade')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='P2PReceivedItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('skin_name', models.CharField(max_length=200)),
                ('value', models.DecimalField(decimal_places=2, help_text='Agreed value of this skin.', max_digits=12)),
                ('inventory_item', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='p2p_received_line', to='core.inventoryitem')),
                ('trade', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='received_lines', to='core.p2ptrade')),
            ],
            options={
                'ordering': ['id'],
            },
        ),
    ]
