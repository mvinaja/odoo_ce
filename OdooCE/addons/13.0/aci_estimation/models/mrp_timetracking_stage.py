# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class MrpTimetrackingStage(models.Model):
    _name = 'mrp.timetracking.stage'
    _description = 'mrp.timetracking.stage'
    _rec_name = 'name'

    name = fields.Char('Step Stage', required=True, translate=True)
    base_create = fields.Boolean(default=False)
    fold = fields.Boolean('Folded in Pipeline',
        help='This stage is folded in the kanban view when there are no records in that stage to display.')

    @api.model
    def create(self, vals):
        if 'base_create' not in vals.keys() or not vals['base_create']:
            raise UserError(_("You can't create new stage"))
            return False
        return super(MrpTimetrackingStage, self).create(vals)