# -*- coding: utf-8 -*-

from odoo.tests import common


class TestAciProductCommon(common.SavepointCase):

    @classmethod
    def setUpClass(cls):
        super(TestAciProductCommon, cls).setUpClass()

        # Category related data
        Category = cls.env['product.category']
        cls.category_ce = Category.create({
            'name': 'Cost Engineering',
            'type': 'view'
        })
        cls.category_bom = Category.create({
            'name': 'Bill Of Materials',
            'type': 'view',
            'parent_id': cls.category_ce.id
        })
        cls.category_bg = Category.create({
            'name': 'Budget',
            'type': 'bom',
            'bom_type': 'budget',
            'product_key': 'subcontract',
        })
        cls.category_md = Category.create({
            'name': 'Model',
            'type': 'bom',
            'bom_type': 'model',
            'product_key': 'subcontract',
        })
        cls.category_wo = Category.create({
            'name': 'Workorder',
            'type': 'bom',
            'bom_type': 'workorder',
            'product_key': 'subcontract',
        })
        cls.category_ba = Category.create({
            'name': 'Basic',
            'type': 'bom',
            'bom_type': 'basic',
            'product_key': 'subcontract',
        })
