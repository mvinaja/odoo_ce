# -*- coding: utf-8 -*-

from . import common
from odoo.exceptions import ValidationError

class TestCategory(common.TestAciProductCommon):

    def setUp(self):
        res = super(TestCategory, self).setUp()
        Product = self.env['product.template']

        self.product_ba = Product.create({'name': 'Basic BOM', 'categ_id': self.category_ba.id})

    def test_update_type(self):
        # Cannot change category to type of view when a product use it
        with self.assertRaises(ValidationError):
            self.category_ba.type = 'view'

        # Change from bom to normal type
        self.category_ba.type = 'normal'
        self.category_ba.onchange_type()
        self.assertFalse(self.product_ba.is_bom, 'Product should not be a bill of material.')
        self.assertFalse(self.product_ba.bom_type, 'Product should not have a bill of material type.')

    def test_update_mrp_properties(self):
        self.category_ba.bom_type = 'workorder'
        self.assertEqual(self.category_ba.bom_type, self.product_ba.bom_type, 'Category and product bom type are not the same.')

        self.category_ba.product_key = 'material'
        self.assertEqual(self.product_ba.product_key, 'material', 'Product cost should be type of material.')
