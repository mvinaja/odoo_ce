# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

import pytz
import dateutil

class TimeTrackingActionsWizard(models.TransientModel):
    _name = 'time.tracking.actions.wizard'
    _description = 'time.tracking.actions.wizard'

    time_record = fields.Float('Elapsed Time Unit', store=False)
    time_block = fields.Float(string="Elapsed Time", store=False)
    is_block = fields.Boolean(default=False, store=True)
    time_remaining = fields.Float('Time remaining', store=False)
    activity_ids = fields.One2many('time.tracking.actions.activity', 'action_id', store=True)
    key = fields.Char()
    change_project = fields.Boolean(compute="_compute_change_project")
    block_end_date = fields.Datetime('Block End Date', compute="_compute_block_end_date")
    block_end_hour = fields.Datetime('Block End Hour', compute="_compute_block_end_date")
    record_type = fields.Char(compute='_compute_record_type')

    # Single Record
    tracking_id = fields.Many2one('mrp.workcenter.productivity')
    qty_operators = fields.Integer(related='tracking_id.qty_operators', readonly=False)
    production_id = fields.Many2one('mrp.production', compute='_compute_production')
    product_id = fields.Many2one(related='tracking_id.product_id', readonly=True)
    tracking_origin = fields.Selection(related='tracking_id.tracking_origin', readonly=True)
    step_id = fields.Many2one(related='tracking_id.step_id', readonly=True)
    workorder_id = fields.Many2one(related='tracking_id.workorder_id', readonly=True)
    product_type = fields.Selection(related='product_id.step_type', readonly=True)
    add_value = fields.Boolean(related='product_id.add_value', readonly=True)
    infinite_qty = fields.Boolean(related='production_id.bom_id.type_qty', readonly=True)
    analytic_id = fields.Many2one(related='tracking_id.analytic_id')
    qty_expected = fields.Float(related='tracking_id.timetracking_id.expected_qty')
    qty_product = fields.Float(related='tracking_id.timetracking_id.product_qty')
    timetracking_id = fields.Many2one(related='tracking_id.timetracking_id')
    set_operators = fields.Boolean(related='workcenter_id.set_operators')
    workcenter_id = fields.Many2one(related='timetracking_id.workcenter_id')
    department_id = fields.Many2one(related='workcenter_id.employee_id.department_id')
    progress = fields.Integer(default=0)
    qty_progress = fields.Float()
    qty_reference = fields.Float(compute="_compute_reference")
    qty_accumulated = fields.Float(compute="_compute_accumulated")
    employee_ids = fields.One2many('mrp.timetracking.mixed.employee.wizard', 'realtime_id')
    wo_step_ids = fields.Many2many('lbm.work.order.step', string='Steps (optional)')
    note = fields.Text(string='Notes')
    input_type = fields.Selection([('total', 'Finish'),
                                   ('partial', 'Partial')], required=True, default='total')
    step_count = fields.Integer(compute='_compute_step_count')
    note = fields.Text(string='Notes')
    accum_qty = fields.Float(related='timetracking_id.progress_qty')
    accum_progress = fields.Integer(related='timetracking_id.percent_complete')
    product_uom_id = fields.Many2one('uom.uom', string='Product UoM',
                                     related='timetracking_id.product_id.uom_id')
    input_result = fields.Selection([('normal', 'Normal'), ('exceed', 'Exceed')], compute='_compute_input_result',
                                    store=True)
    worked_duration = fields.Float(string='H/H')

    @api.model
    def default_get(self, values):
        Block = self.env['hr.productivity.block']
        res = super(TimeTrackingActionsWizard, self).default_get(values)
        context = self._context
        key = context.get('key', [])
        if key:
            res_ids = []
            key = key[0]
            tracking_ids = self.env['mrp.workcenter.productivity'].search([('key', '=', key)])
            res['key'] = key
            track_id = None
            for tracking_id in tracking_ids:
                if tracking_id.tracking_origin == 'step' and tracking_id.step_id:
                    _id = self.env['time.tracking.actions.activity'].create({'tracking_id': tracking_id.id,
                                                                             'key': key})
                    res_ids.append(_id.id)
                    track_id = tracking_id
                elif tracking_id.tracking_origin == 'workorder':
                    _id = self.env['time.tracking.actions.activity'].create({'tracking_id': tracking_id.id,
                                                                             'key': key})
                    res_ids.append(_id.id)
                    track_id = tracking_id
            res['is_block'] = False if len(res_ids) == 1 else True

            employee_ids = []
            employee_ids.append((0, False, {'employee_id': tracking_id.timetracking_id.workcenter_id.employee_id.id}))
            for employee_id in tracking_id.timetracking_id.workcenter_id.employee_ids.ids:
                start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)

                if Block.search([('employee_id', '=', employee_id),
                                 ('final_start_date', '>=', start),
                                 ('final_start_date', '<=', end)]):
                    employee_ids.append((0, False, {'employee_id': employee_id}))
            res['tracking_id'] = track_id.id
            res['employee_ids'] = employee_ids
            res['activity_ids'] = res_ids
        return res

    @api.depends('activity_ids')
    def _compute_change_project(self):
        for _id in self:
            analytic_ids = self.get_coincident_analytic(_id.activity_ids)
            _id.change_project = True if len(analytic_ids) >= 1 else False

    @api.depends('qty_progress', 'qty_product', 'progress', 'record_type')
    def _compute_input_result(self):
        for r in self:
            if r.record_type == 'progress_qty':
                qty_progress = r.progress * r.qty_product / 100
            elif r.record_type == 'progress_unit':
                qty_progress = r.progress * 1 / 100
            else:
                qty_progress = r.qty_progress

            qty_new = r.timetracking_id.progress_qty + qty_progress
            qty_limit = r.qty_product
            r.input_result = 'exceed' if round(qty_new, 2) > round(qty_limit, 2) else 'normal'

    @api.depends('key')
    def _compute_block_end_date(self):
        for _id in self:
            tracking_ids = self.env['mrp.workcenter.productivity'].search([('key', '=', _id.key)]).sorted(lambda r: r.final_start_date)
            block_ids = self.env['hr.productivity.block'].search([('final_start_date', '<=', tracking_ids[0].final_start_date),
                                                                 ('final_end_date', '>=', tracking_ids[0].final_start_date),
                                                                 ('employee_id', 'in',
                                                                  tracking_ids.mapped('employee_id').ids)])
            block_ids.sorted(lambda r: r.final_end_date, reverse=True)
            _id.block_end_date = block_ids[0].final_end_date
            _id.block_end_hour = block_ids[0].final_end_date

    @api.depends('activity_ids')
    def _compute_record_type(self):
        for _id in self:
            if self.is_block:
                activity_type = list(set(_id.activity_ids.mapped('record_type')))
                if len(activity_type) == len(list(set(activity_type) & set(['progress_qty', 'progress_unit']))):
                    record_type = 'progress'
                elif len(activity_type) == len(list(set(activity_type) & set(['unit', 'float', 'integer']))):
                    record_type = 'number'
                else:
                    record_type = 'mixed'
            else:
                if self.product_type in ['progress_qty', 'progress_unit']:
                    record_type = 'progress'
                else:
                    record_type = 'number'
            _id.record_type = record_type

    @api.depends('tracking_origin', 'tracking_id')
    def _compute_production(self):
        for r in self:
            r.production_id = r.tracking_id.production_id.id if r.tracking_origin == 'workorder' else r.tracking_id.production_by_step.id

    def _compute_reference(self):
        for r in self:
            if r.tracking_origin == 'step':
                rate = r.step_id.rate
            else:
                # ToDo, Change rate = r.workorder_id.rate if r.workorder_id.rate else 1
                rate = 1
            time, num_key = self.env['time.tracking.actions.wizard'].get_time_record(r.key)
            qty_reference = round(rate * (time / 3600000), 2)
            if r.record_type == 'unit':
                qty_reference = 1
            elif r.record_type == 'integer':
                qty_reference = int(qty_reference)
            r.qty_reference = qty_reference

    def _compute_accumulated(self):
        for r in self:
            if r.tracking_origin == 'step':
                workcenter_id = r.step_id.wkcenter
                origin = 'step'
                field = 'step_id'
                _id = r.step_id.id
            else:
                workcenter_id = r.workorder_id.resource_id
                origin = 'workorder'
                field = 'workorder_id'
                _id = r.workorder_id.id

            period_group_id = workcenter_id.period_group_id.id

            period_id = self.env['payment.period'].search([('group_id', '=', period_group_id),
                                                           ('to_date', '>=', datetime.now()),
                                                           ('from_date', '<=', datetime.now())])

            tracking_ids = self.env['mrp.workcenter.productivity'].search([('period_id', '=', period_id.id),
                                                                           (field, '=', _id),
                                                                           ('tracking_origin', '=', origin)])
            r.qty_accumulated = round(sum(tracking_ids.mapped('qty_progress')), 2)

    @api.onchange('workorder_id')
    def onchange_workorder_id(self):
        return {'domain': {'wo_step_id': [('id', 'in',
                                           self.workorder_id.step_ids.filtered(lambda r: r.available_wo_qty_progress > 0).ids)]}}

    @api.onchange('wo_step_id')
    def onchange_wo_step_id(self):
        self.qty_progress = self.wo_step_id.available_wo_qty_progress
        self.progress = self.qty_progress * 100 / self.workorder_id.qty_production

    def build_action(self, view_id=None):
        if not view_id:
            view_id = self.env['ir.model.data'].get_object(
                'aci_estimation', 'time_tracking_actions_single_wizard_form_view')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'res_model': 'time.tracking.actions.wizard',
            'name': 'Register Activity//small',
            'target': 'new',
            'res_id': self.id
        }

    def reload(self, view_id=None):
        if not view_id:
            view_id = self.env['ir.model.data'].get_object(
                'aci_estimation', 'time_tracking_actions_single_wizard_form_view')
        return {
            'name': 'Register Activity//small',
            'res_model': 'time.tracking.actions.wizard',
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.id
        }

    # Calculator methods
    def show_calculator(self, model_name, field_name, res_id, res_value, mode):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Calculator//small',
            'res_model': 'mrp.estimation.calculator',
            'target': 'new',
            'context': {'default_model_name': model_name,
                        'default_field_name': field_name,
                        'default_res_id': res_id,
                        'default_float_result': res_value,
                        'default_int_result': res_value,
                        'default_mode': mode,
                        'return_action': self.build_action()}
        }

    def show_worked_duration_calculator_btn(self, context=None):
        return self.show_calculator('time.tracking.actions.wizard', 'worked_duration', self.id, self.worked_duration, 'float')

    def show_qty_operators_calculator_btn(self, context=None):
        return self.show_calculator('time.tracking.actions.wizard', 'qty_operators', self.id, self.qty_operators, 'integer')

    def show_progress_calculator_btn(self, context=None):
        return self.show_calculator('time.tracking.actions.wizard', 'progress', self.id, self.progress, 'integer')

    def show_qty_progress_calculator_btn(self, context=None):
        return self.show_calculator('time.tracking.actions.wizard', 'qty_progress', self.id, self.qty_progress, 'float')

    def calculate_by_progress(self, progress):
        if self.product_type not in ('progress_qty', 'progress_unit'):
            self.qty_progress = self.qty_product * progress
        else:
            self.progress = progress * 100

    def calculate_25(self):
        self.calculate_by_progress(.25)
        return self.build_action()

    def calculate_50(self):
        self.calculate_by_progress(.50)
        return self.build_action()

    def calculate_75(self):
        self.calculate_by_progress(.75)
        return self.build_action()

    def calculate_100(self):
        self.calculate_by_progress(1)
        return self.build_action()

    def calculate_balance(self):
        accumulated_progress = self.timetracking_id.percent_wo_complete
        ratio = (100 - accumulated_progress) / 100
        if self.timetracking_id.tracking_origin == 'workorder':
            progress = ratio
        else:
            ratio = ratio if ratio < self.timetracking_id.step_id.tracking_ratio else self.timetracking_id.step_id.tracking_ratio
            progress = ratio * 100 / self.timetracking_id.step_id.tracking_ratio
        self.calculate_by_progress(progress if progress > 0 else 0)
        return self.build_action()

    def get_coincident_analytic(self, activity_ids):
        change_analytic = []
        coincident_analytic_ids = []
        for activity_id in activity_ids:
            if activity_id.production_id.type == 'operational' or activity_id.production_id.project_id:
                change_analytic.append(False)
            else:
                _workcenter_id = activity_id.step_id.wkcenter if activity_id.tracking_origin == 'step' else activity_id.workorder_id.resource_id
                analytic_ids = [activity_id.mapped('production_id').project_id.id]
                workcenter_ids = self.env['mrp.estimation.workcenter'].search([('workcenter_id', '=', _workcenter_id.id)])
                active_analytic_ids = workcenter_ids.analytic_ids.filtered(lambda r: r.analytic_id.id in analytic_ids and
                                                                                           r.status == 'unlocked').mapped(
                    'analytic_id').ids
                change_analytic.append(True if len(active_analytic_ids) >= 1 else False)
                if change_analytic.count(True) == 1:
                    coincident_analytic_ids = active_analytic_ids
                elif change_analytic.count(True) > 1:
                    coincident_analytic_ids = list(set(coincident_analytic_ids) & set(active_analytic_ids))
        return list(set(coincident_analytic_ids) - set(activity_ids.mapped('analytic_id').ids))

    def get_time_block(self, key):
        tracking_ids = self.env['mrp.workcenter.productivity'].search([('key', '=', key)])
        block_date_start = tracking_ids.sorted(lambda r: r.date_start)[0].date_start
        return abs((datetime.now() - block_date_start).total_seconds()) * 1000

    def get_time_record(self, key):
        block_duration = self.get_time_block(key)
        tracking_ids = self.env['mrp.workcenter.productivity'].search([('key', '=', key)])
        tracking_origin = tracking_ids[0].tracking_origin
        qty = len(tracking_ids)
        if tracking_origin == 'step':
            tracking_ids = tracking_ids.filtered(lambda r: r.step_id != "" or r.step_id is not None)
            qty = len(tracking_ids)/2
        return block_duration / qty, qty

    def validate_data(self, tracking_id, tracking_origin, record_type, qty_product, qty_progress, progress, qty_operators,
                      product_id, step_id, workorder_id, infinite_qty, timetracking_id, set_operators=False,
                      worked_duration=0, employee_ids=[], wanted_date=None, note=None, wo_step_id=None, qty_status='pending', available=True,
                      forecast=False):
        Block = self.env['hr.productivity.block']
        if record_type == 'progress_qty':
            qty_progress = progress * qty_product / 100
        elif record_type == 'progress_unit':
            qty_progress = progress * 1 / 100
        else:
            progress = qty_progress * 100 / qty_product

        if record_type == 'unit' and qty_progress != 1:
            raise UserError(_('QTY Progress for {} must be 1'.format(product_id.name)))
        elif record_type == 'integer' and qty_progress != float(qty_progress):
            raise UserError(_('QTY Progress for {} must be integer'.format(product_id.name)))
        elif qty_progress == 0:
            raise UserError(_('QTY Progress for {} must be bigger than 0'.format(product_id.name)))
        elif progress == 0:
            raise UserError(_('Progress for {} must be bigger than 0'.format(product_id.name)))

        if qty_operators != len(employee_ids) and set_operators:
            raise ValidationError(_('The employee list must be equal to {}'.format(qty_operators)))

        if tracking_origin == 'step':
            _workcenter_id = step_id.wkcenter.id
            _object_id = step_id
            _args = ('step_id', '=', _object_id.id)
        elif tracking_origin == 'workorder':
            _workcenter_id = workorder_id.resource_id.id
            _object_id = workorder_id
            _args = ('workorder_id', '=', _object_id.id)
        qty_ids = self.env['mrp.workcenter.productivity'].search([_args])
        if not infinite_qty and \
                sum(qty_ids.mapped('qty_progress')) + qty_progress > _object_id.product_qty:
            raise UserError(_('The wanted QTY for {} is bigger than '
                              'the Product QTY of the M.O.'.format(product_id.name)))

        if record_type in ('progress_unit', 'progress_qty'):
            input_type = 'progress'
        else:
            input_type = 'qty'

        if tracking_origin == 'step':
            qty_limit = timetracking_id.step_id.tracking_ratio * timetracking_id.workorder_id.qty_production
            wo_qty_progress = qty_progress * qty_limit / timetracking_id.step_id.product_qty if timetracking_id.step_id.product_qty > 0 else 0
            qty_current = sum(timetracking_id.step_id.tracking_ids.mapped('wo_qty_progress'))
        elif tracking_origin == 'workorder':
            qty_limit = timetracking_id.workorder_id.qty_production
            wo_qty_progress = qty_progress
            qty_current = sum(timetracking_id.workorder_id.tracking_ids.mapped('qty_progress'))
        valid_operation = True if qty_current + wo_qty_progress <= qty_limit else False
        valid_qty = True

        if not infinite_qty and (not valid_operation or not valid_qty):
            raise ValidationError(_('The wanted QTY for {} is bigger/lower than permitted'.format(self.timetracking_id.
                                                                                            product_id.complete_name)))
        if qty_operators > 1 and set_operators:
            start = wanted_date.replace(hour=0, minute=0, second=0, microsecond=0)
            end = wanted_date.replace(hour=23, minute=59, second=59, microsecond=0)
            for employee_id in employee_ids.mapped('employee_id'):
                if not Block.search([('employee_id', '=', employee_id.id),
                                     ('final_start_date', '>=', start),
                                     ('final_start_date', '<=', end),
                                     ('block_available', '=', True)]):
                    raise ValidationError(_('{} does not have an activity block on this day'.format(employee_id.name)))
            record = (progress, qty_progress, qty_operators, input_type, 'add', worked_duration,
                      employee_ids.mapped('employee_id').ids, note, wo_step_id.id if wo_step_id else None, qty_status, available)
        else:
            record = (progress, qty_progress, qty_operators, input_type, 'add', worked_duration,
                      [], note, wo_step_id.id if wo_step_id else None, qty_status, available, forecast)
        return {_object_id.id: record}

    def finish_approval_btn(self, restrict=False):
        self.finish_btn(qty_status='waiting_approval')

    def finish_blocked_btn(self, restrict=False):
        self.finish_btn(available=False)

    def finish_blocked_btn(self, restrict=False):
        self.finish_btn(qty_status='waiting_approval', forecast=True)

    def finish_btn(self, restrict=False, qty_status='pending', available=True, forecast=False):
        start = datetime.now()
        Tworkorder = self.env['mrp.timetracking.workorder']
        tracking_data = {}
        if self.is_block:
            timetracking_ids = self.activity_ids.mapped('tracking_id').mapped('timetracking_id')
            keys = self.activity_ids.mapped('key')
            for activity_id in self.activity_ids:
                tracking_origin = activity_id.tracking_origin
                tracking_data.update(self.validate_data(activity_id.tracking_origin, activity_id.record_type,
                                                        activity_id.qty_product, activity_id.qty_progress,
                                                        activity_id.progress, activity_id.qty_operators,
                                                        activity_id.product_id, activity_id.step_id,
                                                        activity_id.workorder_id, activity_id.infinite_qty,
                                                        activity_id.timetracking_id, activity_id.worked_duration,
                                                        wanted_date=start, qty_status=qty_status))
                if restrict:
                    period_id = activity_id.workorder_id.resource_id.period_group_id.period_ids.filtered(
                        lambda _r: _r.from_date < start <= _r.to_date)
                    Tworkorder.search([('workorder_id', '=', activity_id.workorder_id.id),
                                       ('period_id', '=', period_id.id)]).write({'is_closed': True})

            timetracking_id = activity_id.timetracking_id
        else:
            if self.step_count == 1:
                wo_step_id = self.wo_step_ids[0]
            else:
                wo_step_id = None
            tracking_data.update(self.validate_data(self.tracking_id, self.tracking_origin, self.product_type, self.qty_product,
                                                    self.qty_progress, self.progress, self.qty_operators, self.product_id, self.step_id,
                                                    self.workorder_id, self.infinite_qty, self.timetracking_id,
                                                    self.set_operators, self.worked_duration,
                                                    employee_ids=self.employee_ids, note=self.note,
                                                    wanted_date=start, wo_step_id=wo_step_id, qty_status=qty_status,
                                                    available=available, forecast=forecast))
            tracking_origin = self.tracking_origin
            timetracking_ids = self.tracking_id.timetracking_id
            timetracking_id = self.tracking_id.timetracking_id
            keys = [self.key]
            if restrict:
                period_id = self.workcenter_id.period_group_id.period_ids.filtered(
                    lambda _r: _r.from_date < start <= _r.to_date)
                Tworkorder.search([('workorder_id', '=', self.workorder_id.id),
                                   ('period_id', '=', period_id.id)]).write({'is_closed': True})

        start = self.env['time.tracking.actions'].validate_time(start, timetracking_id, None,
                                                                'end')
        self.env['time.tracking.actions'].send_to_todo([self.key], 'ToDo', tracking_origin, start,
                                                       'manual', False, tracking_data)

        restriction_record_ids = self.env['time.tracking.actions'].get_restriction(timetracking_ids)
        if restriction_record_ids:
            to_return = self.env['time.tracking.actions'].open_form_restriction(restriction_record_ids, tracking_origin,
                                                                                keys)
        else:
            to_return = None

        context = self._context
        previous_activity = context.get('previous_activity', [])
        if previous_activity:
            args = context.get('args', [])
            _ids = self.env['mrp.timetracking'].browse(args[0])
            start = datetime.now()
            key = self.env['time.tracking.actions'].send_to_working(tracking_origin, _ids, start, args[3], args[4])
            # Check Activity
            check_ids = _ids.filtered(lambda r: r.step_type == 'check')
            if check_ids:
                self.env['time.tracking.actions'].send_to_todo([key], 'ToDo', tracking_origin, start,
                                                               'automatic')
        return to_return

    def finish_restrict_btn(self):
        return self.finish_btn(True)

    def new_project(self):
        self.finish_btn()
        view_id = self.env['ir.model.data'].get_object('aci_estimation', 'tracking_new_analytic_form_view').id
        analytic_ids = self.get_coincident_analytic(self.activity_ids)
        return {
            'name': _('Start with other Analytic Account'),
            'res_model': 'tmp.tracking.new.analytic',
            'type': 'ir.actions.act_window',
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': {'analytic_ids': analytic_ids,
                        'default_key': self.key}
        }

    def button_block(self):
        view_id = self.env['ir.model.data'].get_object('aci_estimation', 'hr_productivity_block_tree_view').id
        employee_ids = self.env['mrp.workcenter.productivity'].search([('key', '=', self.key)]).mapped('employee_id').ids
        return {
            'name': _('Adjust Blocks'),
            'res_model': 'hr.productivity.block',
            'type': 'ir.actions.act_window',
            'views': [(view_id, 'tree')],
            'target': 'current',
            'domain': [('employee_id', 'in', employee_ids),
                       ('final_start_date', '>=', self.block_end_date.replace(hour=0, minute=0, second=0)),
                       ('final_start_date', '<=', self.block_end_date.replace(hour=23, minute=59, second=59))]}

    def show_step_btn(self, input_type, field_name):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_mixed_step_wizard')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'view_mode': 'form',
            'name': 'Steps//small',
            'res_model': 'mrp.timetracking.mixed.step.wizard',
            'target': 'new',
            'context': {'default_input_type': input_type,
                        'default_workorder_id': self.workorder_id.id,
                        'default_field_name': field_name,
                        'default_multi_field_name': 'wo_step_ids',
                        'default_model_name': 'time.tracking.actions.wizard',
                        'default_timetracking_id': self.timetracking_id.id,
                        'default_res_id': self.id,
                        'return_action': self.build_action()}
        }

    def show_progress_step_btn(self, context=None):
        return self.show_step_btn('progress', 'progress')

    def show_qty_progress_step_btn(self, context=None):
        return self.show_step_btn('qty', 'qty_progress')

    @api.depends('wo_step_ids')
    def _compute_step_count(self):
        for r in self:
            r.step_count = len(r.wo_step_ids)

    @api.onchange('input_type')
    def onchange_input_type(self):
        if self.input_type == 'total':
            return self.calculate_balance()
        elif self.input_type == 'partial':
            self.qty_progress = sum(self.wo_step_ids.mapped('available_wo_qty_progress'))
            self.progress = self.qty_progress * 100 / self.workorder_id.qty_production
            return self.reload()

class TimeTrackingActionsActivity(models.TransientModel):
    _name = 'time.tracking.actions.activity'
    _description = 'time.tracking.actions.activity'

    action_id = fields.Many2one('time.tracking.actions.wizard')
    key = fields.Char()
    tracking_id = fields.Many2one('mrp.workcenter.productivity')
    production_id = fields.Many2one('mrp.production', compute='_compute_production')
    product_id = fields.Many2one(related='tracking_id.product_id', readonly=True)
    tracking_origin = fields.Selection(related='tracking_id.tracking_origin', readonly=True)
    step_id = fields.Many2one(related='tracking_id.step_id', readonly=True)
    workorder_id = fields.Many2one(related='tracking_id.workorder_id', readonly=True)

    record_type = fields.Selection(related='product_id.step_type', readonly=True)
    add_value = fields.Boolean(related='product_id.add_value', readonly=True)
    infinite_qty = fields.Boolean(related='production_id.bom_id.type_qty', readonly=True)

    analytic_id = fields.Many2one(related='tracking_id.analytic_id')
    qty_expected = fields.Float(related='tracking_id.timetracking_id.expected_qty')
    qty_product = fields.Float(related='tracking_id.timetracking_id.product_qty')
    timetracking_id = fields.Many2one(related='tracking_id.timetracking_id')
    progress = fields.Float(default=0)
    qty_progress = fields.Float()
    qty_reference = fields.Float(compute="_compute_reference")
    qty_accumulated = fields.Float(compute="_compute_accumulated")

    def _compute_accumulated(self):
        for r in self:
            if r.tracking_origin == 'step':
                workcenter_id = r.step_id.wkcenter
                origin = 'step'
                field = 'step_id'
                _id = r.step_id.id
            else:
                workcenter_id = r.workorder_id.resource_id
                origin = 'workorder'
                field = 'workorder_id'
                _id = r.workorder_id.id

            period_group_id = workcenter_id.period_group_id.id

            period_id = self.env['payment.period'].search([('group_id', '=', period_group_id),
                                                           ('to_date', '>=', datetime.now()),
                                                           ('from_date', '<=', datetime.now())])

            tracking_ids = self.env['mrp.workcenter.productivity'].search([('period_id', '=', period_id.id),
                                                                           (field, '=', _id),
                                                                           ('tracking_origin', '=', origin)])
            r.qty_accumulated = round(sum(tracking_ids.mapped('qty_progress')), 2)

    @api.depends('tracking_origin', 'tracking_id')
    def _compute_production(self):
        for r in self:
            r.production_id = r.tracking_id.production_id.id if r.tracking_origin == 'workorder' else r.tracking_id.production_by_step.id

    def _compute_reference(self):
        for r in self:
            if r.tracking_origin == 'step':
                rate = r.step_id.rate
            else:
                # ToDo, Change rate = r.workorder_id.rate if r.workorder_id.rate else 1
                rate = 1
            time, num_key = self.env['time.tracking.actions.wizard'].get_time_record(r.key)
            qty_reference = round(rate * (time / 3600000), 2)
            if r.record_type == 'unit':
                qty_reference = 1
            elif r.record_type == 'integer':
                qty_reference = int(qty_reference)
            r.qty_reference = qty_reference

    @api.onchange('progress')
    def onchange_year(self):
        if self.progress < 0:
            self.progress = 0
        elif self.progress > 100:
            self.progress = 100


class TimeTrackingActions(models.Model):
    _name = 'time.tracking.actions'
    _description = 'time.tracking.actions'

    # Method with WorkOrder and Step tracking
    def generate_workcenter_block(self, workcenter_ids, wanted_date):
        Blocks = self.env['hr.productivity.block']
        wanted_date_start = wanted_date.strftime('%Y-%m-%d 00:00:00')
        wanted_date_end = wanted_date.strftime('%Y-%m-%d 23:59:59')
        for workcenter_id in workcenter_ids:
            block_ids = Blocks.search([('employee_id', '=', workcenter_id.employee_id.id),
                                       ('final_start_date', '>=', wanted_date_start),
                                       ('final_start_date', '<=', wanted_date_end),
                                       ('incidence_id', '=', False)])
            if not block_ids:
                Blocks.generate_blocks(wanted_date, workcenter_id)
                Blocks.rebuild_blocks(workcenter_id.employee_id)

    def open_form_qty(self, key, previous_activity, args):
        if len(args[0]) == 1:
            view_id = self.env['ir.model.data'].get_object('aci_estimation',
                                                           'time_tracking_actions_single_wizard_form_view')
            title = 'Register Activity//small'
        else:
            view_id = self.env['ir.model.data'].get_object('aci_estimation',
                                                           'time_tracking_actions_wizard_form_view')
            title = _('Register Activity')
        self = self.with_context(key=key, previous_activity=previous_activity, args=args)
        return {
            'name': title,
            'res_model': 'time.tracking.actions.wizard',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'target': 'new',
            'context': self._context,
        }

    def open_form_restriction(self, restriction_ids, model, key):
        view_id = self.env['ir.model.data'].get_object('aci_estimation', 'mrp_timetracking_restriction_wizard_form_view')
        restriction_ids = self.env['mail.activity'].browse(restriction_ids)
        _id = self.env['mrp.timetracking.restriction.wizard'].create(
            {'restriction_ids': [(0, 0, {'activity_id': r.id}) for r in restriction_ids]})
        if model == 'step':
            args = [('key', 'in', key), ('tracking_origin', '=', 'step')]
        elif model == 'workorder':
            args = [('key', 'in', key), ('tracking_origin', '=', 'workorder')]
        elif model == 'activity':
            args = [('key', 'in', key), ('tracking_origin', '=', 'activity')]
        working_records = self.env['mrp.workcenter.productivity'].search(args)
        self = self.with_context(productivity_records=working_records.ids)
        return {
            'name': _('Release Restriction'),
            'res_model': 'mrp.timetracking.restriction.wizard',
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'target': 'new',
            'res_id': _id.id,
            'context': self._context,
        }

    def open_form_blocked(self, checked_ids, model, args):
        form_view_id = self.env['ir.model.data'].get_object('aci_estimation', 'mrp_timetracking_form_view_quality')
        return {
            'name': _('Quality Alert'),
            'res_model': 'mrp.timetracking',
            'type': 'ir.actions.act_window',
            'views': [(form_view_id.id, 'form')],
            'target': 'new',
            'res_id': checked_ids[0]
        }

    # ############################################ Validation Methods
    def validate_selection_number(self, model, ids):
        if model == 'workorder':
            return True
        for workcenter_id in ids.mapped('workcenter_id'):
            workcenter_step_ids = ids.filtered(lambda r: r.workcenter_id == workcenter_id)
            if len(workcenter_step_ids) > workcenter_id.activity_group_limit:
                raise UserError(_('Exceeded maximum number of activities for {} in a block ({})'.format(workcenter_id.name,
                                                                                                   workcenter_id.activity_group_limit)))
        return True

    def validate_selection_stage(self, ids, from_stage):
        stage_id = self.get_stage_id(from_stage)
        stage_ids = ids.mapped('stage_id').ids
        if stage_ids.count(stage_id) != len(stage_ids):
            raise UserError(_('A selected object is currently in a differente stage. Check your selected items'))
        return True

    def validate_selection_type(self, ids):
        if len(ids) > 1 and ids.filtered(lambda r: r.step_type == 'check') > 1:
            raise UserError(_('You can not mix Check Activity with other types'))

    def validate_selection_qty(self, ids):
        for _id in ids:
            if _id.progress_qty >= _id.product_qty and _id.tracking_origin != 'activity':
                raise UserError(_('{} has reached its maximum qty accepted of {}'.\
                                  format(_id.product_id.complete_name, _id.product_qty)))
            if round(_id.percent_wo_complete) >= 100:
                raise UserError(_('{} has reached its maximum qty accepted of {}'.\
                                  format(_id.product_id.complete_name, _id.product_qty)))

    def validate_estimation(self, workcenter_ids, ids, wanted_date):
        Estimation = self.env['mrp.estimation']
        Tworkorder = self.env['mrp.timetracking.workorder']
        for workcenter_id in workcenter_ids:
            timetracking_ids = ids.filtered(lambda r: r.workcenter_id.id == workcenter_id.id)
            warehouse_ids = ids.mapped('warehouse_id')
            for period_group_id in timetracking_ids.mapped('period_group_id'):
                period_id = period_group_id.period_ids.filtered(lambda _r: _r.from_date < wanted_date <= _r.to_date)
                estimation_ids = Estimation.search([('period_group_id', '=', period_group_id.id),
                                                   ('workcenter_id', '=', workcenter_id.id),
                                                   ('period_id', '=', period_id.id),
                                                   ('estimation_type', '=', 'period'),
                                                   ('warehouse_id', 'in', warehouse_ids.ids)])
                for estimation_id in estimation_ids:
                    if estimation_id.period_status not in ('draft', 'open'):
                        raise UserError(_('{} cannot do this input because his/her estimation is closed'.\
                                        format(workcenter_id.employee_id.name)))
                    for workorder_id in timetracking_ids.mapped('workorder_id'):
                        tworkorder_id = Tworkorder.search([('workorder_id', '=', workorder_id.id),
                                                           ('ite_period_id', '=', period_id.id),
                                                           ('ite_progress', '>', 0)])
                        if tworkorder_id and tworkorder_id.is_closed:
                            raise UserError(_('{} cannot do this input because the workorder {} is closed'.\
                                            format(workcenter_id.employee_id.name, workorder_id.name)))
                        elif not tworkorder_id:
                            raise UserError(_('{} cannot do this input because the workorder {} cannot '
                                              'have inputs on this period.'.\
                                            format(workcenter_id.employee_id.name, workorder_id.name)))

    def generate_workcenter_block(self, workcenter_ids, wanted_date):
        Blocks = self.env['hr.productivity.block']
        wanted_date_start = wanted_date.strftime('%Y-%m-%d 00:00:00')
        wanted_date_end = wanted_date.strftime('%Y-%m-%d 23:59:59')
        for workcenter_id in workcenter_ids:
            block_ids = Blocks.search([('employee_id', '=', workcenter_id.employee_id.id),
                                       ('final_start_date', '>=', wanted_date_start),
                                       ('final_start_date', '<=', wanted_date_end),
                                       ('incidence_id', '=', False)])
            past_block_ids = Blocks.search([('employee_id', '=', workcenter_id.employee_id.id),
                                            ('final_start_date', '<', wanted_date_start),
                                            ('status', '=', 'draft')])
            if not block_ids:
                Blocks.generate_blocks(wanted_date, workcenter_id)
            if past_block_ids:
                past_block_ids.write({'status': 'closed'})

    def validate_workcenter_block(self, workcenter_ids, wanted_date, validate_current=True):
        Blocks = self.env['hr.productivity.block']
        Productivity = self.env['mrp.workcenter.productivity']
        inactive_block_ids = []
        empty_block_ids = []
        for workcenter_id in workcenter_ids:
            block_ids = Blocks.search([
                ('final_start_date', '>=', datetime.today().replace(hour=0, minute=0, second=0, microsecond=1)),
                ('final_end_date', '<=', datetime.today().replace(hour=23, minute=59, second=59, microsecond=1)),
                ('employee_id', '=', workcenter_id.employee_id.id)], order='final_start_date')
            found_block = False
            block_id = None
            for block in block_ids:
                start = block.final_start_date
                end = block.final_end_date
                if start <= wanted_date <= end:
                    if block.block_type == 'inactive':
                        inactive_block_ids.append(workcenter_id.name)
                    found_block = True
                    block_id = block

            if validate_current:
                running_block_activity = Productivity.search([('employee_id', '=', workcenter_id.employee_id.id),
                                                              ('final_end_date', '=', False),
                                                              ('final_start_date', '>=', block_id.final_start_date)])
                if not running_block_activity:
                    busy_activity = Productivity.search([('employee_id', '=', workcenter_id.employee_id.id),
                                                         ('final_start_date', '>=', block_id.final_start_date),
                                                         ('final_start_date', '<=', wanted_date),
                                                         ('final_end_date', '>', wanted_date)],
                                                         order='final_start_date DESC')

                    if busy_activity:
                        diff = fields.Datetime.from_string(busy_activity[0].final_end_date) - fields.Datetime.from_string(
                            wanted_date)
                        tz_wanted_date = self.env['time.tracking.actions'].get_tz_datetime(wanted_date, self.env.user)
                        tz_activity_end = self.env['time.tracking.actions'].get_tz_datetime(busy_activity[0].final_end_date,
                                                                                              self.env.user)

                        raise UserError(_('{} would finish an activity in {} minutes. ({} to {}).'.
                                          format(workcenter_id.employee_id.name, round(diff.total_seconds() / 60.0, 2),
                                                 tz_wanted_date.strftime('%H:%M'),
                                                 tz_activity_end.strftime('%H:%M'))))

                    daily_activity = Productivity.search([('employee_id', '=', workcenter_id.employee_id.id),
                                                          ('final_start_date', '>=', block_id.final_start_date),
                                                          ('final_end_date', '<=', wanted_date)],
                                                       order='final_start_date DESC')
                    last_activity_start = daily_activity[0].final_end_date if daily_activity else None
                    if not last_activity_start and wanted_date.replace(second=0, microsecond=0) > \
                            block_id.final_end_date.replace(second=0, microsecond=0):
                        diff = fields.Datetime.from_string(wanted_date) - fields.Datetime.from_string(
                            block_id.final_end_date)
                        tz_wanted_date = self.env['time.tracking.actions'].get_tz_datetime(wanted_date, self.env.user)
                        tz_block_start = self.env['time.tracking.actions'].get_tz_datetime(block_id.final_end_date,
                                                                                                   self.env.user)

                        raise UserError(_('{} has {} minutes to fill in his/her block ({} to {}).'.
                                          format(workcenter_id.employee_id.name, round(diff.total_seconds() / 60.0, 2),
                                                 tz_block_start.strftime('%H:%M'),
                                                 tz_wanted_date.strftime('%H:%M'))))
                    elif last_activity_start and wanted_date.replace(second=0, microsecond=0) > \
                        last_activity_start.replace(second=0, microsecond=0):
                        diff = fields.Datetime.from_string(wanted_date) - fields.Datetime.from_string(
                            last_activity_start)
                        if round(diff.total_seconds() / 60.0, 2) > 10:
                            tz_wanted_date = self.env['time.tracking.actions'].get_tz_datetime(wanted_date, self.env.user)
                            tz_last_activity_start = self.env['time.tracking.actions'].get_tz_datetime(last_activity_start, self.env.user)
                            raise UserError(_('{} has {} minutes to fill in his/her block ({} to {})'.
                                              format(workcenter_id.employee_id.name, round(diff.total_seconds() / 60.0, 2),
                                                     tz_last_activity_start.strftime('%H:%M'),
                                                     tz_wanted_date.strftime('%H:%M'))))

            if not found_block:
                empty_block_ids.append(workcenter_id.name)
            if inactive_block_ids and validate_current:
                raise UserError(_('The next Employees are currently in'
                                  ' an inactive block: {}'.format(', '.join(inactive_block_ids))))
            if empty_block_ids and validate_current:
                raise UserError(_('The next Employees does not have a block: {}'.format(', '.join(empty_block_ids))))
        return True

    def validate_category_productive(self):
        unproductive_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'unproductive')],
                                                                              limit=1)
        if not unproductive_id:
            raise UserError(_('An unproductive category is needed on the list of productivity.'
                              'Create one from the Manufacturing app, menu: Configuration / Productivity Losses.'))

        productive_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'productive')], limit=1)
        if not productive_id:
            raise UserError(_('A productive category is needed on the list of productivity.'
                              ' Create one from the Manufacturing app, menu: Configuration / Productivity Losses.'))
        loss_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'performance')], limit=1)
        if not loss_id:
            raise UserError(_('A performance category is needed on the list of productivity.'
                              ' Create one from the Manufacturing app, menu: Configuration / Productivity Losses.'))

        return True

    def validate_restriction(self, ids):
        if ids.mapped('workorder_id').filtered(lambda r: r.can_be_planned is False):
            raise UserError(_('This Activity has an active Restriction'))

    def validate_time(self, date, tracking_ids, manual_data, time_type='start'):
        Productivity = self.env['mrp.workcenter.productivity']
        if manual_data and time_type == 'start':
            date = manual_data['date_start']
        elif manual_data:
            date = manual_data['date_end']
        if time_type == 'start':
            productivity_ids = Productivity.search([('resource_id', 'in', tracking_ids.mapped('workcenter_id').ids),
                                                    ('final_start_date', '<=', date),
                                                    ('final_end_date', '>=', date)], order='final_start_date ASC')
            if productivity_ids:
                raise UserError(_('Currently there is an activity registered on this time ({}):\n {}'.
                                  format(self.env['time.tracking.actions'].get_tz_datetime(date, self.env.user), ', '.join(productivity_ids.timetracking_id.product_id.mapped('complete_name')))))
        else:
            productivity_ids = Productivity.search([('resource_id', 'in', tracking_ids.mapped('workcenter_id').ids),
                                                    ('final_end_date', '=', None)])
            if productivity_ids:
                activity_start = productivity_ids[0].final_start_date
                productivity_ids = Productivity.search([('resource_id', 'in', tracking_ids.mapped('workcenter_id').ids),
                                                        ('final_start_date', '>', activity_start)], order='final_start_date ASC')
                if productivity_ids:
                    date = productivity_ids[0].final_start_date
        return date

    def get_restriction(self, tracking_ids):
        workcenter_ids = tracking_ids.mapped('workcenter_id')
        product_ids = tracking_ids.mapped('product_id')
        restriction_ids = self.env['mail.activity'].search([('tracking_state', '=', 'locked'),
                                                            ('activity_source', '!=', 'normal'),
                                                            ('workcenter_ids', 'in', [workcenter_ids.ids[0]]),
                                                            ('product_id', 'in', product_ids.ids)])
        if restriction_ids:
            return restriction_ids.ids
        return None

    def get_working_record(self, workcenter_ids):
        for workcenter_id in workcenter_ids:
            wo_tracking_ids = self.env['mrp.workcenter.productivity'].search([('tracking_origin', '=', 'workorder'),
                                                                              ('final_end_date', '=', None),
                                                                              ('resource_id', '=',
                                                                               workcenter_id.id)])
            _wo_ids = wo_tracking_ids.mapped('timetracking_id')

            step_tracking_ids = self.env['mrp.workcenter.productivity'].search([('tracking_origin', '=', 'step'),
                                                                                ('final_end_date', '=', None),
                                                                                (
                                                                                'resource_id', '=', workcenter_id.id)])
            _step_ids = step_tracking_ids.mapped('timetracking_id')

            if _step_ids:
                return [_id.key for _id in step_tracking_ids]

            if _wo_ids:
                return [_id.key for _id in wo_tracking_ids]

    def validate_workcenter_activity(self, workcenter_ids, start):
        for workcenter_id in workcenter_ids:

            wo_tracking_ids = self.env['mrp.workcenter.productivity'].search([('tracking_origin', '=', 'workorder'),
                                                                              ('final_end_date', '=', None),
                                                                              ('resource_id', '=', workcenter_id.id)])
            _wo_ids = wo_tracking_ids.mapped('timetracking_id')

            step_tracking_ids = self.env['mrp.workcenter.productivity'].search([('tracking_origin', '=', 'step'),
                                                                                ('final_end_date', '=', None),
                                                                                ('resource_id', '=', workcenter_id.id)])
            _step_ids = step_tracking_ids.mapped('timetracking_id')

            if _step_ids:
                _ids_direct = _step_ids.filtered(lambda r: r.product_id.step_type == 'unit' or r.product_id.step_type == 'check')
                if len(_ids_direct) == len(_step_ids):
                    self.send_to_todo([_id.key for _id in step_tracking_ids], 'ToDo', 'step', start, 'automatic')
                    return None
                else:
                    return [_id.key for _id in step_tracking_ids]

            if _wo_ids:
                _ids_direct = _wo_ids.filtered(lambda r: r.product_id.step_type == 'unit' or r.product_id.step_type == 'check')
                if len(_ids_direct) == len(_wo_ids):
                    self.send_to_todo([_id.key for _id in wo_tracking_ids], 'ToDo', 'workorder', start, 'automatic')
                    return None
                else:
                    return [_id.key for _id in wo_tracking_ids]

    def send_to_todo(self, keys, to_stage, model, end_date, record_type, calculate_qty=True, tracking_data=None, manual_data={}):
        if model == 'step':
            args = [('key', 'in', keys), ('tracking_origin', '=', 'step')]
            origin = ('tracking_origin', '=', 'step')
            type = ('workorder_id', '=', None)
        elif model == 'workorder':
            args = [('key', 'in', keys), ('tracking_origin', '=', 'workorder')]
            origin = ('tracking_origin', '=', 'workorder')
            type = ('tracking_origin', '=', 'workorder') # Trash data
        working_records = self.env['mrp.workcenter.productivity'].search(args)
        record_data = []
        prod_by_key = {}
        prod_by_wc = {}
        taken_wo = []  # multistep key_diff is the same in all the steps,
        # I need to validate if I already used that wo
        # Get elements and quantity by key
        for record in working_records:
            if model == 'step':
                working_wo = self.env['mrp.workcenter.productivity'].search(
                    [('key_diff', '=', record.key_diff),
                     ('step_id', '=', False)])
                valid_working_wo = working_wo
                if len(working_wo) > 1:
                    found_wo = False
                    for wo in working_wo:
                        if not found_wo and wo.id not in taken_wo:
                            valid_working_wo = wo
                            taken_wo.append(wo.id)
                            found_wo = True
                _workcenter_id = record.step_id.workorder_id.resource_id.id
            elif model == 'workorder':
                valid_working_wo = None
                _workcenter_id = record.workorder_id.resource_id.id
            record_data.append([record, valid_working_wo, record.key, _workcenter_id])
            prod_by_key.update(
                {record.key: prod_by_key[record.key] + 1}) if record.key in prod_by_key \
                else prod_by_key.update({record.key: 1})
            prod_by_wc.update(
                {_workcenter_id: prod_by_wc[_workcenter_id] + 1}) if _workcenter_id in prod_by_wc \
                else prod_by_wc.update({_workcenter_id: 1})

        # Calculate dateEnd by key
        wc_check_out_date = {}
        key_check_out_date = {}
        block = self.env['hr.productivity.block']
        for record in working_records:
            if model == 'step':
                _workcenter_id = record.step_id.workorder_id.resource_id
            elif model == 'workorder':
                _workcenter_id = record.workorder_id.resource_id
            record_start = record.date_start
            block_ids = block.search([('employee_id', '=', _workcenter_id.employee_id.id)], order='final_start_date')
            for block in block_ids:
                start = block.final_start_date
                end = block.final_end_date
                if start <= record_start <= end:
                    if end_date < end:
                        wc_check_out_date.update({_workcenter_id.id: end_date})
                    else:
                        wc_check_out_date.update({_workcenter_id.id: end})

            if record.key not in key_check_out_date:
                productivity = self.env['mrp.workcenter.productivity'].search(
                    [('key', '=', record.key), origin, type])

                for prod in productivity:
                    if model == 'step':
                        _workcenter_id = prod.step_id.workorder_id.resource_id.id
                    elif model == 'workorder':
                        _workcenter_id = prod.workorder_id.resource_id.id
                    if _workcenter_id in wc_check_out_date:
                        end_date = wc_check_out_date[_workcenter_id] if wc_check_out_date[
                                                                           _workcenter_id] < end_date else end_date
                key_check_out_date.update({record.key: end_date})

        # Calculate durations by wc (in seconds)
        duration_by_wc = {}
        for record in working_records:
            if model == 'step':
                _workcenter_id = record.step_id.workorder_id.resource_id.id
            elif model == 'workorder':
                _workcenter_id = record.workorder_id.resource_id.id
            if _workcenter_id not in duration_by_wc:
                duration = key_check_out_date[record.key] - record.date_start
                duration_hours = duration.total_seconds()
                duration_by_wc.update({_workcenter_id: duration_hours / prod_by_wc[_workcenter_id]})

        # Calculate QTY progress by record ID
        qty_progress = {}
        if calculate_qty:
            for record in working_records:
                if model == 'step':
                    _workcenter_id = record.step_id.workorder_id.resource_id.id
                    _object_id = record.step_id
                    _args = [('step_id', '=', record.id)]
                elif model == 'workorder':
                    _workcenter_id = record.workorder_id.resource_id.id
                    _object_id = record.workorder_id
                    _args = [('workorder_id', '=', record.id), ('tracking_origin', '=', 'workorder')]
                if _object_id.id not in qty_progress:
                    qty_ids = self.env['mrp.workcenter.productivity'].search(_args)
                    duration_by_wkcenter = duration_by_wc[_workcenter_id] / 3600

                    qty = _object_id.rate * duration_by_wkcenter if model == 'step' else duration_by_wkcenter
                    product_type = _object_id.product_id.step_type
                    if product_type in ('unit', 'check'):
                        qty = 1
                    elif product_type == 'integer':
                        qty = int(qty) if int(qty) != 0 else 1

                    if _object_id.production_id.bom_id.type_qty is False:
                        if sum(qty_ids.mapped('qty_progress')) + qty > _object_id.product_qty:
                            qty = _object_id.product_qty - sum(qty_ids.mapped('qty_progress'))
                            if product_type in ('unit', 'check'):
                                qty = 1
                            elif product_type == 'integer':
                                qty = int(qty)
                    if duration_by_wkcenter == 0:
                        qty_progress.update({_object_id.id: 0})
                    else:
                        qty_progress.update({_object_id.id: qty})

        # STEP DATA
        # [0] PRODUCTIVITY STEP
        # [1] PRODUCTIVITY WORKORDER
        # [2] KEY
        # [3] WORKCENTER
        record_data.sort(key=lambda x: (x[2], x[3]))
        current_wc = 0
        stage_id = self.get_stage_id(to_stage)
        for data in record_data:
            if model == 'step':
                _workcenter_id = data[0].step_id.wkcenter.id
            elif model == 'workorder':
                _workcenter_id = data[0].workorder_id.resource_id.id

            date_start = data[0].date_start if current_wc != data[3] \
                else date_start + dateutil.relativedelta.relativedelta(
                seconds=duration_by_wc[_workcenter_id])
            calculated_date_end = date_start + dateutil.relativedelta.relativedelta(
                seconds=duration_by_wc[_workcenter_id])
            if date_start >= calculated_date_end:
                # Something is wrong ...
                calculated_date_end = date_start

            if model == 'step':
                _id = data[0].step_id
                _workorder_id = data[0].step_id.workorder_id
                _step_id = data[0].step_id
            elif model == 'workorder':
                _id = data[0].workorder_id
                _workorder_id = data[0].workorder_id
                _step_id = None
            if calculate_qty:
                _progress = 100
                _qty_progress = qty_progress[_id.id]
                _qty_operators = data[0].step_id.min_members
                _input_type = 'qty'
                _input_category = 'add'
            else:
                _progress = tracking_data[_id.id][0]
                _qty_progress = tracking_data[_id.id][1]
                _qty_operators = tracking_data[_id.id][2]
                _input_type = tracking_data[_id.id][3]
                _input_category = tracking_data[_id.id][4]

            if not manual_data:
                _note = tracking_data[_id.id][7]
                duration = self.env['lbm.scenario'].get_duration_by_calendar(
                    self.env['mrp.workcenter'].browse([_workcenter_id]).resource_calendar_id,
                    self.env['time.tracking.actions'].get_tz_datetime(date_start, self.env.user),
                    self.env['time.tracking.actions'].get_tz_datetime(calculated_date_end, self.env.user))
                _worked_duration = tracking_data[_id.id][5] if _qty_operators != 1 else duration
                if _worked_duration < duration or _worked_duration > duration * _qty_operators:
                    raise ValidationError(_('Worked duration must be betweeen {} to {} min.'.format(round(duration, 2),
                                                                                                    round(
                                                                                                        duration * _qty_operators,
                                                                                                        2))))

                record_values = {'date_start': date_start,
                               'date_end': calculated_date_end,
                               'qty_operators': _qty_operators,
                               'progress': _progress,
                               'qty_progress': _qty_progress,
                               'type': record_type,
                               'input_type': _input_type,
                               'input_category': _input_category,
                               'worked_duration': _worked_duration,
                               'employee_ids': [(6, False, tracking_data[_id.id][6])],
                               'note': _note}
                if tracking_data[_id.id][8]:
                    record_values.update({'step_id': tracking_data[_id.id][8]})
                if tracking_data[_id.id][9]:
                    record_values.update({'qty_status': tracking_data[_id.id][9]})
                if tracking_data[_id.id][10]:
                    record_values.update({'available': tracking_data[_id.id][10]})
                if tracking_data[_id.id][11]:
                    record_values.update({'forecast': tracking_data[_id.id][11]})
            else:
                record_values = {'date_start': manual_data['date_start'],
                                 'date_end': manual_data['date_end'],
                                 'qty_operators': manual_data['qty_operators'],
                                 'progress': manual_data['progress'],
                                 'qty_progress': manual_data['qty_progress'],
                                 'type': record_type,
                                 'worked_duration': manual_data['worked_duration'],
                                 'input_type': manual_data['input_type'],
                                 'input_category': manual_data['input_category'],
                                 'note': manual_data['note'],
                                 'forecast': manual_data['forecast'],
                                 'qty_status': manual_data['qty_status'],
                                 'available': manual_data['available'],
                                 'employee_ids': [(6, False, manual_data['employee_ids'])],
                                 'restriction_ids': [(6, False, manual_data['restriction_ids'])]}
                if manual_data['wo_step_id']:
                    record_values.update({'step_id': manual_data['wo_step_id']})

                restriction_ids = self.env['mail.activity'].browse(manual_data['restriction_ids'])
                restriction_ids.write({'tracking_state': 'unlocked',
                                       'solved_date': datetime.today().strftime(DEFAULT_SERVER_DATE_FORMAT)})
            data[0].write(record_values)
            if data[1]:
                data[1].write(record_values)
            data[0].timetracking_id.write({'stage_id': stage_id})
            current_wc = data[3]

            if not manual_data:
                data[0].write({'input_ids': [(0, False, {'date_start': data[0].date_start,
                                                         'date_end': data[0].date_end,
                                                         'qty_progress': data[0].qty_progress})]})
            else:
                data[0].write({'input_ids': manual_data['input_ids']})

    # ############################################# Process Methods
    def send_to_working(self, model, ids, start, to_stage, args_extra):
        # originally this method used ModelName since we could send to working from different models
        # now, all come from mrp.timetracking
        tracking_record = args_extra
        key = '{}.{}.{}.{}.{}.{}.{}.{}.{}.{}.{}.{}.{}'.format(start.year, start.month, start.day,
                                               start.hour, start.minute, start.second, start.microsecond,
                                               datetime.now().year, datetime.now().month, datetime.now().day,
                                               datetime.now().hour, datetime.now().minute, datetime.now().microsecond)
        tracking_record.update({'date_start': start,
                                'user_id': self.env.user.id,
                                'key': key})

        for _id in ids:
            _workcenter_id = _id.workcenter_id
            _workcenter_template_id = _id.workcenter_id.template_id
            _workorder_id = _id.workorder_id
            key_diff = key

            # Loss_ID is old code.
            if not _id.product_id.product_tmpl_id.productivity_type == 'improductive':
                loss_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'productive')],
                                                                              limit=1)[0]
            else:
                loss_id = self.env['mrp.workcenter.productivity.loss'].search([('loss_type', '=', 'unproductive')],
                                                                              limit=1)
            base_record = self.build_tracking_record(_workcenter_template_id, _workcenter_id, key_diff, start, loss_id, model)
            tracking_record.update(base_record)
            tracking_record.update({'analytic_id': _id.analytic_id.id})

            qty_operators = self.env['lbm.workorder'].search([('workorder_id', '=', _workorder_id.id)],
                                                             limit=1).operators_qty

            _id.workorder_id.state = 'progress'
            if model == 'step':
                tracking_step = {**tracking_record, **{'timetracking_id': _id.id,
                                                       'step_id': _id.step_id.id,
                                                       'pay_amount': _workorder_id.direct_cost,
                                                       'qty_operators': qty_operators,
                                                       'description': _('Step Time Tracking: ') + self.env.user.name}}
                step = self.env['mrp.workcenter.productivity'].create(tracking_step)
                _id.tracking_ids = [(4, step.id)]
            else:
                tracking_workorder = {**tracking_record, **{'timetracking_id': _id.id,
                                                            'workorder_id': _workorder_id.id,
                                                            'pay_amount': _workorder_id.direct_cost,
                                                            'qty_operators': qty_operators,
                                                            'description': _('WO Time Tracking: ') + self.env.user.name}}

                workorder = self.env['mrp.workcenter.productivity'].create(tracking_workorder)

                _id.tracking_ids = [(4, workorder.id)]
                # Horrible Hack
                workorder.step_id = None

            _id.stage_id = self.get_stage_id(to_stage)
        return key

    # ############################################# Tools

    def build_tracking_record(self, _workcenter_template_id, _workcenter_id, key_diff, start, loss_id, origin):
        return {'workcenter_id': _workcenter_template_id.id,
                'resource_id': _workcenter_id.id,
                'employee_id': _workcenter_id.employee_id.id,
                'employee_ids': [],
                'key_diff': key_diff,
                'period_id': self.get_period(_workcenter_id, start),
                'loss_id': loss_id.id,
                'is_productivity': False if loss_id.loss_type == "unproductive" else True,
                'imputed_by_employee_id': self.get_imputed_employee(),
                'tracking_origin': origin}

    def get_stage_id(self, stage_name):
        return self.env['mrp.timetracking.stage'].search([('name', '=', stage_name)], limit=1).id

    def get_tz_datetime(self, datetime, user_id):
            Params = self.env['ir.config_parameter']
            tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
            tz = Params.get_param('tz') if tz_param else None
            if tz:
                tz_datetime = datetime.astimezone(pytz.timezone(str(tz)))
            else:
                user_id = user_id if user_id else self.env.user
                # if not user_id.tz:
                #     raise UserError(_('TimeZone Error. Check your profile configuration.'))
                tz = str(user_id.tz) if user_id.tz else 'Mexico/General'
                tz_datetime = datetime.astimezone(pytz.timezone(tz))
            return tz_datetime

    def remove_tz_datetime(self, datetime, user_id):
            Params = self.env['ir.config_parameter']
            tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
            user_id = user_id if user_id else self.env.user
            tz = Params.get_param('tz') if tz_param else user_id.tz or 'Mexico/General'
            return pytz.timezone(tz).localize(datetime.replace(tzinfo=None), is_dst=False).astimezone(
                pytz.UTC).replace(tzinfo=None)

    def get_float_hour(self, date):
        return float('{0}.{1}'.format(date.hour, date.minute))

    def get_imputed_employee(self):
        imputed_employee_id = self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)], limit=1)
        return imputed_employee_id.id

    def move_to_stage(self, checked_ids, modelName, from_stage, to_stage, args_extra, manual_data={}):
        start = datetime.now()
        ids = self.env['mrp.timetracking'].browse(checked_ids)
        workcenter_ids = ids.mapped('workcenter_id')
        tracking_type = ids.mapped('tracking_origin')[0] if ids else None
        #  ***********  Validation process
        #  ***********  Currently we use 10 different validations.
        if to_stage == 'Working':
            #  1. Selected IDS are inside the maximum allowed
            self.validate_selection_number(tracking_type, ids)
            #  2. Check if one of the selected IDS have a different stage that what we selected (from stage)
            self.validate_selection_stage(ids, from_stage)
            #  3. Check if the user is not trying to mix check types
            self.validate_selection_type(ids)
            if not manual_data:
                #  4. ToDo. Validate Qty of selected IDS
                self.validate_selection_qty(ids)
                # 5. Validate if period and/or estimation is closed
                self.validate_estimation(workcenter_ids, ids, start)
                #  6. Generate blocks (if first tracking of the day) then Validate workcenter block (we need actives blocks)
                self.generate_workcenter_block(workcenter_ids, start)
            self.validate_workcenter_block(workcenter_ids, start, False if manual_data else True)
            #  7. Validate Workcenters contract
            self.validate_workcenter_contract(workcenter_ids, ids)
            #  8. Validate if we have productivity loss categories
            self.validate_category_productive()
            # 9. Validate that it doesn't have an active restriction
            self.validate_restriction(ids)
            # 10. Since we can do tracking directly, we need to validate that the current time is not "used"
            start = self.validate_time(start, ids, manual_data, 'start')

        #  ***********  Change stage process
        #  ***********  Currently we use 5 different user cases.
        if from_stage == 'ToDo' and to_stage == 'Working':
            pending_keys = self.validate_workcenter_activity(workcenter_ids, start)
            if not pending_keys:
                key = self.send_to_working(tracking_type, ids, start, to_stage, args_extra)
                check_ids = ids.filtered(lambda r: r.step_type == 'check')
                if check_ids:
                    restriction_record_ids = self.get_restriction(ids)
                    self.env['time.tracking.actions'].send_to_todo([key], 'ToDo', tracking_type,
                                                                   start, 'automatic')
                    if restriction_record_ids:
                        to_return = ['open_form_restriction', restriction_record_ids, tracking_type, [key]]
                    else:
                        to_return = None
                else:
                    if manual_data:
                        self.env['time.tracking.actions'].send_to_todo([key], 'ToDo', tracking_type,
                                                                       start, 'automatic', manual_data=manual_data)
                    to_return = None
            else:
                to_return = ['open_form_qty', pending_keys, True,
                             [checked_ids, 'mrp.timetracking', from_stage, to_stage, args_extra]]
        elif from_stage == 'Working' and to_stage == 'ToDo':
            start = self.validate_time(start, ids, manual_data, 'end')
            restriction_record_ids = self.get_restriction(ids)
            working_records = self.get_working_record(workcenter_ids)
            pending_keys = self.validate_workcenter_activity(workcenter_ids, start)
            if pending_keys:
                to_return = ['open_form_qty', pending_keys, False,
                             [checked_ids, 'mrp.timetracking', from_stage, to_stage, args_extra]]
            else:
                if restriction_record_ids:
                    to_return = ['open_form_restriction', restriction_record_ids, tracking_type, working_records]
                else:
                    to_return = None
        elif from_stage == 'ToDo' and to_stage == 'Blocked':
            to_return = ['open_form_blocked', checked_ids, modelName, None]
        elif from_stage == 'ToDo' and to_stage == 'Finished':
            ids.write({'stage_id': self.get_stage_id('Finished')})
            to_return = None
        else:
            to_return = None
        return to_return

    # End of methods with WorkOrder and Step tracking

    def validate_workcenter_contract(self, workcenter_ids, record_ids):
        for workcenter_id in workcenter_ids:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', workcenter_id.employee_id.id),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            if not contract_id:
                raise UserError(
                    _('The Employee {} does not have a running contract'.format(workcenter_id.employee_id.name)))
            if not contract_id.analytic_account_id and record_ids.filtered(lambda r: r.baseline_id.type == 'periodic'):
                raise UserError(_('The Contract of the employee {} does not have an Analytic Account'.format(
                    workcenter_id.employee_id.name)))

    def get_period(self, workcenter_id, wanted_date):
        period_group_id = workcenter_id.period_group_id.id
        return self.env['payment.period'].search([('group_id', '=', period_group_id),
                                                  ('to_date', '>=', wanted_date),
                                                  ('from_date', '<=', wanted_date)]).id


class TrackingManagement(models.Model):
    _name = 'tracking.management'
    _description = 'tracking.management'

    loss_id = fields.Many2one('mrp.workcenter.productivity.loss', string='Loss Reason')
    description = fields.Text()

    def button_block(self):
        context = self.env.context
        checked_ids = context.get('checked_ids')
        model = context.get('model')
        self.env[model].browse(checked_ids).write({'stage_id': self.env['time.tracking.actions'].get_stage_id('Blocked')})
