# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class QualityAlert(models.Model):
    _inherit = "quality.alert"

    lock_product = fields.Boolean()
    timetracking_id = fields.Many2one('mrp.timetracking', ondelete='cascade')
    product_ids = fields.Many2many('product.product', string='Product Ids')
    type = fields.Selection([('normal', 'Normal'),
                             ('restriction', 'Restriction'),
                             ('production', 'Production')], default='normal')

    @api.model
    def create(self, vals):
        Tracking = self.env['mrp.timetracking']
        working_stage_id = self.env['time.tracking.actions'].get_stage_id('Working')
        res = super(QualityAlert, self).create(vals)
        if 'lock_product' in vals and 'timetracking_id' in vals:
            if vals.get('lock_product'):
                if Tracking.search([('product_id', '=', vals.get('product_id')),
                                    ('stage_id', '=', working_stage_id),
                                    ('workcenter_id', '=', vals.get('workcenter_id'))]):
                    raise ValidationError(_('Warning! The product you are trying to lock is'
                                            ' currently working'))
                Tracking.search([('product_id', '=', res.product_id.id),
                                 ('workcenter_id', '=', res.workcenter_id.id)]).\
                    write({'stage_id': self.env['time.tracking.actions'].get_stage_id('Blocked')})
        return res

    def write(self, vals):
        res = super(QualityAlert, self).write(vals)
        if 'stage_id' in vals:
            solved_id = self.env['quality.alert.stage'].search([('name', '=', 'Solved')])
            if vals.get('stage_id') == solved_id.id:
                Tracking = self.env['mrp.timetracking']
                quality_alert_ids = self.search([('product_id', '=', self.product_id.id),
                                                 ('workcenter_id', '=', self.workcenter_id.id),
                                                 ('lock_product', '=', True),
                                                 ('stage_id', '!=', solved_id.id),
                                                 ('id', '!=', self.id)]).ids

                if len(quality_alert_ids) == 0:
                    Tracking.search([('product_id', '=', self.product_id.id),
                                     ('workcenter_id', '=', self.workcenter_id.id)]). \
                        write({'stage_id': self.env['time.tracking.actions'].get_stage_id('ToDo')})
        return res

    def unlink(self):
        Tracking = self.env['mrp.timetracking']
        if not self.search([('product_id', 'in', self.product_id.ids),
                            ('workcenter_id', 'in', self.workcenter_id.ids),
                            ('lock_product', '=', True),
                            ('id', '!=', self.ids)]):
            Tracking.search([('product_id', 'in', self.product_id.ids),
                             ('workcenter_id', 'in', self.workcenter_id.ids)]). \
                write({'stage_id': self.env['time.tracking.actions'].get_stage_id('ToDo')})
        super(QualityAlert, self).unlink()