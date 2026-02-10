from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contracts', '0010_alter_firmasigningauditlog_event'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='contract',
            index=models.Index(fields=['tenant_id', 'contract_type'], name='ct_tenant_type_idx'),
        ),
    ]
