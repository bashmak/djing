# -*- coding: utf-8 -*-
# Generated by Django 1.9 on 2016-11-30 15:15
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CountryISOCode',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('long_name', models.CharField(max_length=200)),
                ('iso_3', models.CharField(blank=True, max_length=10)),
                ('iso_2', models.CharField(blank=True, max_length=10)),
            ],
        ),
        migrations.CreateModel(
            name='MapMarker',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('latitude', models.CharField(blank=True, max_length=30)),
                ('longitude', models.CharField(blank=True, max_length=30)),
                ('platinum', models.BooleanField(default=False, verbose_name=b'Platinum Partner')),
                ('contact_name', models.CharField(blank=True, max_length=50)),
                ('contact_title', models.CharField(blank=True, max_length=50)),
                ('airport_name', models.CharField(blank=True, max_length=100)),
                ('airport_code', models.CharField(blank=True, max_length=6)),
                ('address', models.TextField(blank=True, max_length=200)),
                ('city', models.CharField(blank=True, max_length=200)),
                ('state', models.CharField(blank=True, max_length=50)),
                ('zipcode', models.CharField(blank=True, max_length=10)),
                ('phone', models.CharField(blank=True, max_length=40)),
                ('fax', models.CharField(blank=True, max_length=40)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('url', models.URLField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='MarkerCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name=b'type')),
                ('position', models.IntegerField(default=0)),
                ('icon', models.ImageField(blank=True, upload_to=b'gmap-icons/', verbose_name=b'icon')),
                ('platinum_icon', models.ImageField(blank=True, upload_to=b'gmap-icons/', verbose_name=b'platinum icon')),
                ('shadow', models.ImageField(blank=True, upload_to=b'gmap-icons/', verbose_name=b'icon shadow')),
            ],
        ),
        migrations.CreateModel(
            name='MarkerSubCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name=b'Name')),
            ],
        ),
        migrations.CreateModel(
            name='SalesBoundary',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('boundary_code', models.CharField(max_length=75, verbose_name=b'Boundary Code')),
            ],
        ),
        migrations.CreateModel(
            name='SalesDirector',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name=b'Name')),
                ('title', models.CharField(blank=True, max_length=50)),
                ('phone', models.CharField(blank=True, max_length=40, verbose_name=b'Phone Number')),
                ('email', models.EmailField(blank=True, max_length=254, verbose_name=b'Email')),
                ('airport_code', models.CharField(blank=True, max_length=8)),
                ('airport_name', models.CharField(blank=True, max_length=50)),
                ('address', models.TextField(blank=True, max_length=200)),
                ('city', models.CharField(blank=True, max_length=200)),
                ('state', models.CharField(blank=True, max_length=100)),
                ('zipcode', models.CharField(blank=True, max_length=10)),
                ('url', models.URLField(blank=True)),
                ('country', models.ForeignKey(blank=True, on_delete=django.db.models.deletion.CASCADE, to='gmap.CountryISOCode')),
            ],
        ),
        migrations.AddField(
            model_name='salesboundary',
            name='owner',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='gmap.SalesDirector'),
        ),
        migrations.AddField(
            model_name='mapmarker',
            name='category',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='gmap.MarkerCategory'),
        ),
        migrations.AddField(
            model_name='mapmarker',
            name='country',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='gmap.CountryISOCode'),
        ),
        migrations.AddField(
            model_name='mapmarker',
            name='sub_categories',
            field=models.ManyToManyField(related_name='sub_categories', to='gmap.MarkerSubCategory'),
        ),
        migrations.AlterUniqueTogether(
            name='salesboundary',
            unique_together=set([('boundary_code', 'owner')]),
        ),
    ]