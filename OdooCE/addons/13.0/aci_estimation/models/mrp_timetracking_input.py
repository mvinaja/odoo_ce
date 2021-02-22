# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class MrpTimetrackingInput(models.Model):
    _name = "mrp.timetracking.input"
    _description = "Mrp Timetracking Input"

    productivity_id = fields.Many2one('mrp.workcenter.productivity', ondelete='cascade')
    workcenter_id = fields.Many2one(related='productivity_id.workcenter_id')
    workorder_id = fields.Many2one(related='productivity_id.workorder_id')
    step_id = fields.Many2one(related='productivity_id.step_id')
    date_start = fields.Datetime('Start Date')
    date_end = fields.Datetime('End Date')
    qty_progress = fields.Float('Qty. Progress', default=0)
    duration = fields.Float('Duration', compute='_compute_duration', store=True)

    @api.depends('date_end', 'date_start')
    def _compute_duration(self):
        for blocktime in self:
            if blocktime.date_end:
                d1 = fields.Datetime.from_string(blocktime.date_start)
                d2 = fields.Datetime.from_string(blocktime.date_end)
                diff = d2 - d1
                blocktime.duration = round(diff.total_seconds() / 60.0, 2)
            else:
                blocktime.duration = 0.0