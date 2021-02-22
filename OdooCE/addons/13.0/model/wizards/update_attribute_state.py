# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions, _


class UpdateAttributeStateWizard(models.TransientModel):
    _name = 'update.attribute.state.wizard'
    _description = 'Update Attribute State Wizard'

    state = fields.Selection([
        ('draft', 'Draft'),
        ('readonly', 'Approved')
    ], default='draft')

    def update_state_btn(self):
        self.ensure_one()
        context = self.env.context
        Model = self.env[context.get('active_model')]

        selected_ids = Model.browse(context.get('active_ids'))
        selected_ids.write({'state': self.state})
