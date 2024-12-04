from django.db import models


class Dht11(models.Model):
    temp = models.FloatField(null = False)
    hum = models.FloatField(null = False)
    dt = models.DateTimeField(auto_now_add = True,primary_key=True)
    class Meta:
        db_table = 'dht11'  # New table name
