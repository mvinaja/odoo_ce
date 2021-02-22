# -*- coding: utf-8 -*-

from odoo import models, api, fields, _
from odoo.exceptions import ValidationError
import hashlib


class ProductProduct(models.Model):
    _inherit = 'product.product'

    step_type = fields.Selection([
        ('unit', 'Unit'),
        ('integer', 'Integer'),
        ('float', 'Fraction'),
        ('check', 'Check'),
        ('progress_qty', 'Progress x QTY'),
        ('progress_unit', 'Progress x Unit')
    ], default='float', string='Input type')
    is_restriction = fields.Boolean(default=False)
    is_nonconformity = fields.Boolean(default=False)
    is_noncompliance = fields.Boolean(default=False)
    is_quality_control = fields.Boolean(default=False)
    is_pending = fields.Boolean(default=False)
    freecad_key = fields.Char(compute='_compute_freecad_key')

    def unlink(self):
        if self.env['mrp.workcenter.productivity'].search([('product_id', 'in', self.ids)]):
            raise ValidationError(_('You cannot delete a product with tracking.'))
        super(ProductProduct, self).unlink()

    def write(self, vals):
        res = super(ProductProduct, self).write(vals)
        if 'step_type' in vals.keys():
            for _id in self:
                if _id.bom_type != 'workorder' and vals['step_type'] == 'step':
                    raise ValidationError('Only Workorders can depend of the step configuration (step dependant)')
        if 'bom_type' in vals.keys():
            for _id in self:
                if vals['bom_type'] != 'workorder' and _id.step_type == 'step':
                    raise ValidationError('Only Workorders can depend of the step configuration (step dependant)')
        return res

    @api.depends('complete_name')
    def _compute_freecad_key(self):
        for r in self:
            r.freecad_key = hashlib.md5(r.complete_name.encode()).hexdigest()
