# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from datetime import datetime, timedelta
from odoo.exceptions import ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from odoo.http import request


class MrpTimetrackingWorkorderWizard(models.TransientModel):
    _name = 'mrp.timetracking.restriction.wizard'
    _description = 'mrp.timetracking.restriction.wizard'

    restriction_ids = fields.One2many('mrp.timetracking.restriction.list.wizard', 'restriction_id')

    def unlock_restriction_btn(self):
        restriction_ids = self.restriction_ids.filtered(lambda r: r.release_restriction is True).mapped('activity_id')
        restriction_ids.write({'tracking_state': 'unlocked',
                               'solved_date': datetime.today().strftime(DEFAULT_SERVER_DATE_FORMAT)})

        context = self._context
        productivity_records = context.get('productivity_records', [])
        self.env['mrp.workcenter.productivity'].browse(productivity_records).write({'restriction_ids': restriction_ids.ids})


class MrpTimetrackingWorkorderListWizard(models.TransientModel):
    _name = 'mrp.timetracking.restriction.list.wizard'
    _description = 'mrp.timetracking.restriction.list.wizard'

    release_restriction = fields.Boolean(default=False)
    restriction_id = fields.Many2one('mrp.timetracking.restriction.wizard')
    activity_id = fields.Many2one('mail.activity')
    res_id = fields.Char(compute='_compute_res_id')
    product_id = fields.Many2one(related='activity_id.product_id', string='Activity')
    workcenter_id = fields.Many2one(related='activity_id.workcenter_id', string='Workcenter')
    summary = fields.Char(related='activity_id.summary')

    @api.depends('activity_id')
    def _compute_res_id(self):
        for r in self:
            r.res_id = self.env[r.activity_id.res_model].browse([r.activity_id.res_id]).name

class MrpTimetrackingWizard(models.TransientModel):
    _name = 'mrp.timetracking.wizard'
    _description = 'mrp.timetracking.wizard'

    workcenter_id = fields.Many2one('mrp.workcenter')
    employee_id = fields.Many2one('hr.employee')
    description = fields.Text('Description (optional)')
    incidence_date = fields.Datetime(default=datetime.now())

    def end_day_button(self):
        self.ensure_one()
        date_now = datetime.strptime(self.incidence_date, DEFAULT_SERVER_DATETIME_FORMAT)
        if date_now > datetime.now():
            raise ValidationError(_('The date cannot be greater than {}'.format(datetime.now())))
        Blocks = self.env['hr.productivity.block']
        Blocks.end_activity([self.workcenter_id.id], date_now)
        block_ids = Blocks.search([('final_start_date', '>=', self.incidence_date),
                                   ('employee_id', '=', self.employee_id.id)])
        end_incidence = None
        start_incidence = None
        for block_id in block_ids.sorted(key=lambda r: r.final_start_date):
            if not end_incidence:
                end_incidence = block_id.final_end_date
                start_incidence = block_id.final_start_date
            else:
                if end_incidence == block_id.final_start_date:
                    end_incidence = block_id.final_end_date
                else:
                    self.env['attendance.incidence'].create({'check_in': start_incidence,
                                                             'check_out': end_incidence,
                                                             'employee_id': self.employee_id.id,
                                                             'name': self.description,
                                                             'productivity_block': True,
                                                             'approve': False,
                                                             'type_incidence': 'leave'})
                    start_incidence = block_id.final_start_date
                    end_incidence = block_id.final_end_date

        if start_incidence and end_incidence:
            incidence_id = self.env['attendance.incidence'].create({'check_in': start_incidence,
                                                                    'check_out': end_incidence,
                                                                    'employee_id': self.employee_id.id,
                                                                    'name': self.description,
                                                                    'productivity_block': True,
                                                                    'approve': False,
                                                                    'type_incidence': 'leave'})
            incidence_id.write({'state': 'approved'})


class MrpTimetrackingMixedWizardEmployee(models.TransientModel):
    _name = 'mrp.timetracking.mixed.employee.wizard'
    _description = 'mrp.timetracking.mixed.employee.wizard'

    mixed_id = fields.Many2one('mrp.timetracking.mixed.wizard')
    realtime_id = fields.Many2one('time.tracking.actions.wizard')
    department_id = fields.Many2one('hr.department', string="Department")
    employee_id = fields.Many2one('hr.employee')


class MrpTimetrackingMixedStepWizard(models.TransientModel):
    _name = 'mrp.timetracking.mixed.step.wizard'
    _description = 'mrp.timetracking.mixed.step.wizard'

    workorder_id = fields.Many2one('mrp.workorder')
    input_type = fields.Selection([('progress', 'Progress'), ('qty', 'Qty')])
    multi_field_name = fields.Char()
    field_name = fields.Char()
    model_name = fields.Char()
    res_id = fields.Integer()
    step_ids = fields.One2many('mrp.timetracking.mixed.step.list.wizard', 'selector_id')
    timetracking_id = fields.Many2one('mrp.timetracking')
    product_uom_id = fields.Many2one(related='timetracking_id.product_uom_id')
    step_count = fields.Integer(compute='_compute_step_count')
    step_type = fields.Char(compute='_compute_step_type')
    limit = fields.Float(compute='_compute_limit')
    progress = fields.Float(compute='_compute_progress', store=True, readonly=False)
    origin_input_type = fields.Selection([('total', 'Finish'),
                                   ('partial', 'One stp'),
                                   ('fixed', 'Fixed stp %Wo')], required=True, default='total')
    @api.model
    def default_get(self, fields):
        res = super(MrpTimetrackingMixedStepWizard, self).default_get(fields)
        context = self._context
        Step = self.env['mrp.timetracking.mixed.step.list.wizard']
        workorder_id = self.env['mrp.workorder'].browse([context.get('default_workorder_id')])
        _ids = []
        for step_id in workorder_id.step_ids.filtered(lambda r: r.do_tracking is True):
            _ids.append(Step.create({'step_id': step_id.id,
                                     'available_wo_qty_progress': step_id.available_wo_qty_progress}).id)
        res['step_ids'] = [(6, 0, _ids)]
        return res

    @api.depends('step_ids.finished', 'step_ids')
    def _compute_step_count(self):
        for r in self:
            r.step_count = len(r.step_ids.filtered(lambda y: y.finished is True))

    @api.depends('step_count', 'step_ids.finished', 'step_ids')
    def _compute_step_type(self):
        for r in self:
            r.step_type = r.step_ids.filtered(lambda y: y.finished is True)[0].step_id.product_id.step_type if r.step_count == 1 else 'Multi'

    @api.depends('step_count', 'step_type', 'step_ids.finished', 'step_ids')
    def _compute_limit(self):
        for r in self:
            limit = 0
            if r.step_count == 1:
                step_id = r.step_ids.filtered(lambda y: y.finished is True)[0].step_id
                if r.step_type in ('progress_qty', 'progress_unit'):
                    limit = 100 - step_id.percent_complete
                else:
                    limit = step_id.product_qty - step_id.qty_progress
            r.limit = limit

    @api.depends('limit')
    def _compute_progress(self):
        for r in self:
            r.progress = r.limit

    def calculate_input(self):
        result = sum(self.step_ids.filtered(lambda r: r.finished is True).mapped('available_wo_qty_progress'))
        if self.input_type == 'progress':
            result = result * 100 / self.workorder_id.qty_production

        if self.step_count == 1:
            if self.progress > self.limit:
                raise ValidationError(_('Limit exceeded'))

            result = self.progress * result / self.limit

        context = self._context
        action = context.get('return_action')
        self.env[self.model_name].browse([self.res_id]).write({self.field_name: result,
                                                               self.multi_field_name: [(6, 0, self.step_ids.filtered(lambda r: r.finished is True).mapped('step_id').ids)]})
        if action:
            return action

    def calculate_none(self):
        context = self._context
        action = context.get('return_action')
        self.env[self.model_name].browse([self.res_id]).write({self.field_name: 0,
                                                               self.multi_field_name: None})
        if action:
            return action

    def select_all_btn(self):
        self.step_ids.write({'finished': True})
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_mixed_step_wizard')
        context = self._context
        action = context.get('return_action')
        return {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'form')],
            'view_mode': 'form',
            'name': 'Steps//small',
            'res_model': 'mrp.timetracking.mixed.step.wizard',
            'target': 'new',
            'res_id': self.id,
            'context': {'return_action': action}
        }

class MrpTimetrackingMixedStepListWizard(models.TransientModel):
    _name = 'mrp.timetracking.mixed.step.list.wizard'
    _description = 'mrp.timetracking.mixed.step.list.wizard'

    selector_id = fields.Many2one('mrp.timetracking.mixed.step.wizard')
    finished = fields.Boolean()
    step_id = fields.Many2one('lbm.work.order.step')
    available_wo_qty_progress = fields.Float('WO QTY')


class MrpTimetrackingMixedWizard(models.TransientModel):
    _name = 'mrp.timetracking.mixed.wizard'
    _description = 'mrp.timetracking.mixed.wizard'

    timetracking_id = fields.Many2one('mrp.timetracking')
    workorder_id = fields.Many2one(related='timetracking_id.workorder_id')
    tracking_origin = fields.Selection(related='timetracking_id.tracking_origin')
    product_id = fields.Many2one(related='timetracking_id.product_id')
    accum_qty = fields.Float(compute='_compute_accum')
    accum_progress = fields.Integer(compute='_compute_accum')
    record_type = fields.Selection(related='product_id.step_type')
    workcenter_id = fields.Many2one(related='timetracking_id.workcenter_id')
    workcenter_code = fields.Char(compute='_compute_workcenter_code')
    analytic_id = fields.Many2one(related='timetracking_id.analytic_id')
    employee_id = fields.Many2one(related='workcenter_id.employee_id')
    department_id = fields.Many2one(related='workcenter_id.employee_id.department_id')
    input_category = fields.Selection([('add', 'Add'), ('adjust_plus', 'Adjust +'), ('adjust_minus', 'Adjust -')], default='add')
    block_id = fields.Many2one('hr.productivity.block')

    start_date = fields.Datetime(string='Activity Start:')
    max_block_duration = fields.Float(compute='_compute_block_date')
    day_duration = fields.Float(compute='_compute_block_date')
    max_duration = fields.Float(compute='_compute_block_date')
    duration = fields.Float()
    worked_duration = fields.Float(string='H/H')

    product_uom_id = fields.Many2one('uom.uom', string='Product UoM',
                                     related='timetracking_id.product_id.uom_id')
    qty_expected = fields.Float(related='timetracking_id.expected_qty')
    qty_product = fields.Float(related='timetracking_id.product_qty', string='Limit')
    progress = fields.Float(default=0, string="Progress")
    qty_progress = fields.Float(string="Qty")
    qty_operators = fields.Integer(string="Operators")
    restriction_ids = fields.One2many('mrp.timetracking.mixed.restriction.wizard', 'tracking_id')
    unlock_restriction = fields.Boolean(compute='_compute_unlock_restriction')
    input_result = fields.Selection([('normal', 'Normal'), ('exceed', 'Exceed')], compute='_compute_input_result', store=True)
    set_operators = fields.Boolean(related='workcenter_id.set_operators')
    employee_ids = fields.One2many('mrp.timetracking.mixed.employee.wizard', 'mixed_id')

    # Step Selection
    wo_step_ids = fields.Many2many('lbm.work.order.step', string='Steps')
    wo_step_id = fields.Many2one('lbm.work.order.step', string='Step')
    wo_step_type = fields.Selection(related='wo_step_id.product_id.step_type', string='WoStep Type')
    wo_step_product = fields.Many2one(related='wo_step_id.product_id', string='WoStep product')
    wo_step_product_qty = fields.Float(related='wo_step_id.product_qty', string='WoStep qty')
    wo_step_product_uom = fields.Many2one(related='wo_step_id.product_id.uom_id')
    wo_step_progress = fields.Float(default=0, string="Progress")
    wo_step_qty_progress = fields.Float(string="Qty")
    accum_wo_step_qty = fields.Float(compute='_compute_accum')
    accum_wo_step_progress = fields.Integer(compute='_compute_accum')

    note = fields.Text(string='Notes')
    active_on_period = fields.Boolean(related='timetracking_id.active_on_period')
    input_type = fields.Selection([('total', 'Fin.'),
                                   ('single', '%Wo'),
                                   ('fixed', 'Fix.stp'),
                                   ('partial', 'One stp')], required=True, default='total')
    step_count = fields.Integer(compute='_compute_step_count')
    string_value = fields.Char(compute='_compute_string_value')

    @api.model
    def default_get(self, fields):
        res = super(MrpTimetrackingMixedWizard, self).default_get(fields)

        restriction_ids = self.env['mail.activity'].search([('tracking_state', '=', 'locked'),
                                                            ('activity_source', '!=', 'normal'),
                                                            ('workcenter_ids', 'in', [self.workcenter_id.id]),
                                                            ('product_id', 'in', [self.timetracking_id.product_id.id])])

        if restriction_ids:
            _ids = self.env['mrp.timetracking.restriction.wizard'].create(
                {'restriction_ids': [(0, 0, {'activity_id': r.id}) for r in restriction_ids]})
            res['restriction_ids'] = [(6, 0, _ids.ids)]
        return res

    @api.depends('workcenter_id', 'employee_id')
    def _compute_workcenter_code(self):
        for r in self:
            r.workcenter_code = '{}{}'.format(r.workcenter_id.code, ' ({})'.format(r.employee_id.code)
                if r.employee_id.code else '')

    @api.depends('timetracking_id', 'tracking_origin', 'workorder_id', 'wo_step_id')
    def _compute_accum(self):
        for r in self:
            if r.tracking_origin == 'step':
                step_tracking = r.workorder_id.step_ids.tracking_ids
                wo_complete = sum(step_tracking.mapped('wo_qty_progress'))
                limit = self.timetracking_id.step_id.tracking_ratio * self.timetracking_id.workorder_id.qty_production
                percentage = wo_complete * 100 / limit if limit > 0 else 0
                complete = percentage * self.timetracking_id.product_qty / 100
            else:
                wo_tracking = r.workorder_id.tracking_ids.filtered(lambda y: y.tracking_origin == 'workorder')
                step_tracking = r.workorder_id.step_ids.tracking_ids.filtered(lambda y: y.tracking_origin == 'step')
                complete = sum(step_tracking.mapped('wo_qty_progress')) + sum(wo_tracking.mapped('wo_qty_progress'))
                percentage = complete * 100 / r.workorder_id.qty_production
            r.accum_qty = complete
            r.accum_progress = percentage

            if r.wo_step_id:
                wo_accumulated = sum(r.wo_step_id.tracking_ids.mapped('wo_qty_progress'))
                wo_qty = r.wo_step_id.tracking_ratio * r.wo_step_id.workorder_id.qty_production
                r.accum_wo_step_qty = wo_accumulated * r.wo_step_id.product_qty / wo_qty
                r.accum_wo_step_progress = r.accum_wo_step_qty * 100 / r.wo_step_id.product_qty
            else:
                r.accum_wo_step_qty = 0
                r.accum_wo_step_progress = 0

    @api.depends('restriction_ids')
    def _compute_unlock_restriction(self):
        for r in self:
            r.unlock_restriction = True if r.restriction_ids else False

    @api.depends('qty_progress', 'qty_product', 'progress', 'record_type', 'input_category')
    def _compute_input_result(self):
        for r in self:
            if r.record_type == 'progress_qty':
                qty_progress = r.progress * r.qty_product / 100
            elif r.record_type == 'progress_unit':
                qty_progress = r.progress * 1 / 100
            else:
                qty_progress = r.qty_progress
            if r.input_category == 'adjust_minus':
                qty_progress = qty_progress * -1

            qty_new = r.timetracking_id.progress_qty + qty_progress
            qty_limit = r.qty_product
            r.input_result = 'exceed' if round(qty_new, 2) > round(qty_limit, 2) else 'normal'

    @api.depends('block_id', 'timetracking_id', 'start_date')
    def _compute_block_date(self):
        Block = self.env['hr.productivity.block']
        for r in self:
            if self.block_id:
                period_id = self.timetracking_id.workcenter_id.period_group_id.period_ids. \
                    filtered(lambda _r: _r.from_date < self.start_date <= _r.to_date)
                block_ids = Block.search([('employee_id', '=', self.employee_id.id),
                                          ('block_origin', 'in', ('calendar', 'extra')),
                                          ('block_type', '=', 'active'),
                                          ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                                          ('final_end_date', '>=', self.start_date),
                                          ('final_end_date', '<=', period_id.to_date)])
                max_block_date = r.block_id.final_end_date if r.block_id.final_end_date else None
                diff = fields.Datetime.from_string(max_block_date) - fields.Datetime.from_string(r.start_date) \
                    if max_block_date and r.start_date else None
                r.max_block_duration = round(diff.total_seconds() / 60.0, 2) if diff else 0
                total_max_duration = r.max_block_duration + sum(block_ids.mapped('duration'))
                r.max_duration = total_max_duration if total_max_duration > 0.0 else 0.0
                total_day_duration = r.max_block_duration + sum(block_ids.
                                                                filtered(lambda y: y.final_end_date <=
                                                                                   self.start_date.replace(hour=23, minute=59, second=59)).mapped('duration'))
                r.day_duration = total_day_duration if total_day_duration > 0.0 else 0.0
            else:
                r.max_block_duration = 0
                r.max_duration = 0
                r.day_duration = 0

    @api.depends('wo_step_ids')
    def _compute_step_count(self):
        for r in self:
            r.step_count = len(r.wo_step_ids)

    @api.depends('record_type', 'qty_progress', 'progress')
    def _compute_string_value(self):
        for r in self:
            r.string_value = str(round(self.qty_progress, 2)) if r.record_type not in ('progress_qty', 'progress_unit') else str(round(self.progress, 2))

    @api.onchange('duration')
    def onchange_duration(self):
        self.worked_duration = self.duration * self.qty_operators
        return self.reload()

    @api.onchange('qty_operators')
    def onchange_worked_duration(self):
        self.worked_duration = self.duration * self.qty_operators
        return self.reload()

    @api.onchange('input_type')
    def onchange_input_type(self):
        self.progress = None
        self.qty_progress = None
        self.wo_step_id = None
        self.wo_step_ids = None
        if self.input_type == 'total':
            return self.calculate_balance()
        elif self.input_type == 'partial':
            wo_step_id = self.env['lbm.work.order.step'].search([('do_tracking', '=', True),
                                          ('id', 'in', self.workorder_id.step_ids.ids),
                                          ('available_wo_qty_progress', '>', 0)], limit=1)
            if wo_step_id:
                self.wo_step_id = wo_step_id.id
            return self.reload()

    @api.onchange('timetracking_id')
    def onchange_workorder_id(self):
        return {'domain': {'wo_step_id': [('do_tracking', '=', True),
                                          ('id', 'in', self.workorder_id.step_ids.ids),
                                          ('available_wo_qty_progress', '>', 0)]}}

    @api.onchange('wo_step_id')
    def onchange_wo_step_id(self):
        if self.input_type == 'total':
            return self.calculate_balance()
        elif self.input_type == 'partial':
            self.qty_progress = self.wo_step_id.available_wo_qty_progress
            self.progress = self.qty_progress * 100 / self.workorder_id.qty_production
            return self.reload()

    def reload(self, view_id=None):
        if not view_id:
            view_id = self.env['ir.model.data'].get_object(
                'aci_estimation', 'mrp_timetracking_mixed_wizard_form_view')
        return {
            'name': 'Register Activity//small',
            'res_model': 'mrp.timetracking.mixed.wizard',
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.id
        }

    def get_duration_btn(self):
        self.duration = self.max_duration
        return self.reload()

    def get_current_block_duration_btn(self):
        self.duration = self.max_block_duration
        return self.reload()

    def get_current_duration_btn(self):
        seconds = (datetime.now() - self.start_date).total_seconds() / 60
        self.duration = seconds if seconds > 0 else 0
        return self.reload()

    def calculate_by_progress(self, progress):
        if self.record_type not in ('progress_qty', 'progress_unit'):
            self.qty_progress = self.qty_product * progress
        else:
            self.progress = progress * 100

    def calculate_wo_step_by_progress(self, progress):
        if self.wo_step_type not in ('progress_qty', 'progress_unit'):
            self.wo_step_qty_progress = self.wo_step_id.product_qty * progress
        else:
            self.wo_step_progress = progress * 100

    def calculate_25(self):
        self.calculate_by_progress(.25)
        return self.reload()

    def calculate_50(self):
        self.calculate_by_progress(.50)
        return self.reload()

    def calculate_75(self):
        self.calculate_by_progress(.75)
        return self.reload()

    def calculate_step_25(self):
        self.calculate_wo_step_by_progress(.25)
        return self.reload()

    def calculate_step_50(self):
        self.calculate_wo_step_by_progress(.50)
        return self.reload()

    def calculate_step_75(self):
        self.calculate_wo_step_by_progress(.75)
        return self.reload()

    def calculate_100(self):
        self.calculate_by_progress(1)
        return self.reload()

    def calculate_balance(self):
        if self.tracking_origin == 'step':
            step_tracking = self.workorder_id.step_ids.tracking_ids
            wo_complete = sum(step_tracking.mapped('wo_qty_progress'))
            limit = self.timetracking_id.step_id.tracking_ratio * self.timetracking_id.workorder_id.qty_production
            accumulated_progress = wo_complete * 100 / limit if limit > 0 else 0
        else:
            wo_tracking = self.workorder_id.tracking_ids.filtered(lambda y: y.tracking_origin == 'workorder')
            step_tracking = self.workorder_id.step_ids.tracking_ids.filtered(lambda y: y.tracking_origin == 'step')
            complete = sum(step_tracking.mapped('wo_qty_progress')) + sum(wo_tracking.mapped('wo_qty_progress'))
            accumulated_progress = complete * 100 / self.workorder_id.qty_production

        ratio = (100 - accumulated_progress) / 100
        self.calculate_by_progress(ratio if ratio > 0 else 0)
        return self.reload()

    def mixed_tracking_approval_btn(self, restrict=False):
        self.mixed_tracking_btn(qty_status='waiting_approval')

    def mixed_tracking_blocked_btn(self, restrict=False):
        self.mixed_tracking_btn(available=False)

    def mixed_tracking_forecast_btn(self, restrict=False):
        self.mixed_tracking_btn(qty_status='waiting_approval', forecast=True)

    def mixed_tracking_btn(self, restrict=False, qty_status='pending', available=True, forecast=False):
        TrackingAction = self.env['time.tracking.actions']
        Block = self.env['hr.productivity.block']
        Tracking = self.env['mrp.timetracking']
        working_stage_id = self.env['time.tracking.actions'].get_stage_id('Working')
        if self.input_category != 'add':
            self.duration = .0166  # 1 second
            self.qty_operators = 1
            block_id = Block.search(
                [('employee_id', '=', self.employee_id.id),
                 ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                 ('final_start_date', '<=', datetime.now()),
                 ('final_end_date', '>=', datetime.now()),
                 ('block_origin', 'in', ('calendar', 'extra')),
                 ('block_type', '=', 'active')])

            if not block_id:
                today = datetime.now()
                block_ids = Block.search(
                    [('final_end_date', '<=', today),
                     ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                     ('block_origin', 'in', ('calendar', 'extra')),
                     ('block_type', '=', 'active'),
                     ('employee_id', '=', self.employee_id.id)], order='final_end_date DESC')
                block_id = block_ids[0] if block_ids else None
            self.block_id = block_id.id if block_id else None

        if self.wo_step_id:
            if self.wo_step_type == 'progress_qty':
                self.wo_step_qty_progress = self.wo_step_progress * self.wo_step_product_qty / 100
            elif self.wo_step_type == 'progress_unit':
                self.wo_step_qty_progress = self.wo_step_progress / 100
            else:
                self.wo_step_progress = self.wo_step_qty_progress * 100 / self.wo_step_product_qty
            self.progress = self.wo_step_progress * (self.wo_step_id.tracking_ratio * 100) / 100
            self.qty_progress = self.wo_step_qty_progress * (self.wo_step_id.tracking_ratio * self.wo_step_id.workorder_id.qty_production) / self.wo_step_product_qty
        else:
            if self.record_type == 'progress_qty':
                self.qty_progress = self.progress * self.qty_product / 100
            elif self.record_type == 'progress_unit':
                self.qty_progress = self.progress / 100
            else:
                self.progress = self.qty_progress * 100 / self.qty_product

        if self.input_category == 'adjust_minus':
            self.progress = self.progress * -1
            self.qty_progress = self.qty_progress * -1
        if not self.block_id:
            raise ValidationError(_('The activity Block is required'))
        if not self.start_date:
            raise ValidationError(_('Dates are required'))
        if self.duration > self.max_duration:
            raise ValidationError(_('Your maximum duration is {}'.format(self.max_duration)))
        if self.qty_operators <= 0:
            raise ValidationError(_('Write and operator qty'))
        if self.duration <= 0:
            raise ValidationError(_('Write a duration bigger than 0'))
        if self.worked_duration < self.duration or self.worked_duration > self.duration * self.qty_operators:
            raise ValidationError(_('Worked duration must be betweeen {} to {} min.'.format(self.duration, self.duration * self.qty_operators)))
        if self.progress == 0 or self.qty_progress == 0:
            raise ValidationError(_('Missing Progress'))
        if self.qty_operators != len(self.employee_ids) and self.set_operators:
            raise ValidationError(_('The employee list must be equal to {}'.format(self.qty_operators)))
        if Tracking.search([('stage_id', '=', working_stage_id),
                            ('workcenter_id', '=', self.workcenter_id.id)]):
            raise ValidationError(_('This Workcenter has an working activity.'))

        infinite_qty = self.timetracking_id.production_id.bom_id.type_qty

        if self.input_category != 'add':
            Params = self.env['ir.config_parameter']
            over_tracking_param = self.env['ir.config_parameter'].search([('key', '=', 'over_tracking')])
            under_tracking_param = self.env['ir.config_parameter'].search([('key', '=', 'under_tracking')])
            over_tracking = float(Params.get_param('over_tracking')) if over_tracking_param else 0
            under_tracking = float(Params.get_param('under_tracking')) if under_tracking_param else 0
            extra = over_tracking / 100 if self.input_category == 'adjust_plus' else under_tracking / 100
            qty_current = self.timetracking_id.progress_qty
            qty_limit = qty_current * extra
            valid_qty = True if abs(self.qty_progress) <= qty_limit else False
            if self.input_category == 'adjust_plus':
                qty_limit = self.timetracking_id.product_qty
                qty_current = self.timetracking_id.progress_qty
                valid_operation = True if qty_current + self.qty_progress < qty_limit else False
            else:
                valid_operation = True if qty_current - self.qty_progress > 0 else False
        else:

            if self.tracking_origin == 'step' or self.wo_step_id:
                ratio = self.timetracking_id.step_id.tracking_ratio if not self.wo_step_id else self.wo_step_id.tracking_ratio
                qty_progress = self.qty_progress if not self.wo_step_id else self.wo_step_qty_progress
                qty_limit = ratio * self.timetracking_id.workorder_id.qty_production
                step_limit = self.timetracking_id.step_id.product_qty if not self.wo_step_id else self.wo_step_product_qty
                wo_qty_progress = qty_progress * qty_limit / step_limit if step_limit > 0 else 0
                qty_current = sum(self.timetracking_id.step_id.tracking_ids.mapped('wo_qty_progress'))  if not self.wo_step_id else \
                    sum(self.wo_step_id.tracking_ids.mapped('wo_qty_progress'))
            elif self.tracking_origin == 'workorder':
                qty_limit = self.timetracking_id.workorder_id.qty_production
                wo_qty_progress = self.qty_progress
                qty_current = sum(self.timetracking_id.workorder_id.tracking_ids.mapped('qty_progress'))
            valid_operation = True if qty_current + wo_qty_progress <= qty_limit else False
            valid_qty = True

        if not infinite_qty and (not valid_operation or not valid_qty):
            raise ValidationError(_('The wanted QTY for {} is bigger/lower than permitted'.format(self.timetracking_id.
                                                                                            product_id.complete_name)))

        accumulated_progress = self.timetracking_id.percent_wo_complete
        progress = self.progress if self.timetracking_id.tracking_origin == 'workorder' \
            else self.progress * self.timetracking_id.step_id.tracking_ratio
        if accumulated_progress + progress > 100:
            raise ValidationError(_('WorkOrder Progress Exceeded'))

        if request.session.get('session_workcenter'):
            workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
        else:
            workcenter_id = None
        extra_args = {'ip': None,
                      'latitude': None,
                      'longitude': None,
                      'geolocation_message': None,
                      'device': None,
                      'os': None,
                      'employee_id': workcenter_id.employee_id.id if workcenter_id else None,
                      'analytic_id': self.timetracking_id.analytic_id.id}

        if self.record_type in ('progress_unit', 'progress_qty'):
            input_type = 'progress'
        else:
            input_type = 'qty'

        end_date = self.start_date + timedelta(minutes=self.duration)
        complete_record = {'date_start': self.start_date,
                         'date_end': end_date, 'worked_duration': self.worked_duration,
                         'qty_operators': self.qty_operators,
                         'progress': self.progress,
                         'qty_progress': self.qty_progress,
                         'input_type': input_type,
                         'input_category': self.input_category,
                         'note': self.note,
                         'restriction_ids': self.restriction_ids.filtered(lambda r: r.release_restriction is TrackingAction).mapped('activity_id').ids}

        # Build Partitions...
        time_partitions = [{'duration': self.duration, 'worked_duration': self.worked_duration,
                            'start_date': self.start_date,
                            'max_block_duration': self.max_block_duration,
                            'progress': self.progress, 'end_date': end_date,
                            'qty_progress': self.qty_progress}]
        if self.input_type == 'partial':
            time_partitions[0].update({'step_id': self.wo_step_id.id if self.wo_step_id else None})
        elif self.input_type == 'single':
            time_partitions[0].update({'step_id': None})
        elif self.step_count == 0:
            time_partitions[0].update({'step_id': None})
        elif self.step_count == 1:
            time_partitions[0].update({'step_id': self.wo_step_ids[0].id})
        elif self.step_count > 1 and self.input_type == 'fixed':
            time_partitions[0].update({'step_id': None})
            self.wo_step_ids.write({'do_tracking': False})
        else:
            time_partitions = []
            start = self.start_date
            for step_id in self.wo_step_ids:
                duration = round(step_id.tracking_ratio * self.duration, 2)
                worked_duration = round(step_id.tracking_ratio * self.worked_duration, 2)
                block_id = Block.search([('employee_id', '=', self.employee_id.id),
                                         ('block_origin', 'in', ('calendar', 'extra')),
                                         ('block_type', '=', 'active'),
                                         ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                                         ('final_start_date', '<=', start),
                                         ('final_end_date', '>=', start)])
                diff = block_id.final_end_date - start
                max_block_duration = round(diff.total_seconds() / 60.0, 2)
                end_date = self.env['lbm.work.order.step'].get_datetime_by_duration(self.timetracking_id.calendar_id,
                                                                                 start, duration)
                time_partitions.append({
                                  'step_id': step_id.id,
                                  'duration': float(duration),
                                  'worked_duration': float(worked_duration), 'start_date': start,  'end_date': end_date,
                                  'max_block_duration': float(max_block_duration),
                                  'progress': step_id.available_wo_qty_progress * 100 / self.qty_product,
                                  'qty_progress': step_id.available_wo_qty_progress})
                start = end_date + timedelta(seconds=1)

        for tp in time_partitions:
            cmds = []
            complete_record.update({'date_start': tp['start_date']})
            if tp['duration'] < tp['max_block_duration']:
                duration = tp['duration']
            else:
                duration = tp['max_block_duration']
            progress = duration * tp['progress'] / tp['duration']
            qty_progress = progress * tp['qty_progress'] / tp['progress']

            if duration > 0:
                end_date = tp['start_date'] + timedelta(minutes=duration)

                record = {'date_start': tp['start_date'],
                          'date_end': end_date,
                          'qty_progress': qty_progress}

                if self.qty_operators > 1 and self.set_operators:
                    for employee_id in self.employee_ids.mapped('employee_id'):
                        start = tp['start_date'].replace(hour=0, minute=0, second=0, microsecond=0)
                        end = tp['start_date'].replace(hour=23, minute=59, second=59, microsecond=0)

                        if not Block.search([('employee_id', '=', employee_id.id),
                                             ('final_start_date', '>=', start),
                                             ('final_start_date', '<=', end),
                                             ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                                             ('block_available', '=', True)]):
                            raise ValidationError(_('{} does not have an activity block on this day'.format(employee_id.name)))

                    complete_record.update({'employee_ids': self.employee_ids.mapped('employee_id').ids})
                else:
                    complete_record.update({'employee_ids': []})
                cmds.append((0, False, record))
            if tp['duration'] > tp['max_block_duration']:
                period_id = self.timetracking_id.workcenter_id.period_group_id.period_ids. \
                    filtered(lambda _r: _r.from_date < tp['start_date'] <= _r.to_date)
                block_ids = Block.search([('employee_id', '=', self.employee_id.id),
                                          ('block_origin', 'in', ('calendar', 'extra')),
                                          ('block_type', '=', 'active'),
                                          ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                                          ('final_start_date', '>=', tp['start_date']),
                                          ('final_start_date', '<=', period_id.to_date)],  order='final_start_date ASC')
                duration = round(tp['duration'] - tp['max_block_duration'], 2)
                for block_id in block_ids:
                    if duration <= 0:
                        break
                    start_date = block_id.final_start_date
                    if block_id.duration > duration:
                        end_date = start_date + timedelta(minutes=duration)
                        input_duration = duration
                        duration = 0
                    else:
                        end_date = block_id.final_end_date
                        input_duration = block_id.duration
                        duration = duration - block_id.duration

                    progress = input_duration * tp['progress'] / tp['duration']
                    qty_progress = progress * tp['qty_progress'] / tp['progress']

                    record = {'date_start': start_date,
                              'date_end': end_date,
                              'qty_progress': qty_progress}
                    cmds.append((0, False, record))

            complete_record.update({'input_ids': cmds,
                                    'date_end': tp['end_date'],
                                    'forecast': forecast,
                                    'worked_duration': tp['worked_duration'],
                                    'progress': tp['progress'],
                                    'qty_progress': tp['qty_progress'],
                                    'wo_step_id': tp['step_id'],
                                    'available': available,
                                    'qty_status': qty_status})

            TrackingAction.move_to_stage([self.timetracking_id.id], None, 'ToDo', 'Working', extra_args, complete_record)
        if restrict:
            period_id = self.workcenter_id.period_group_id.period_ids.filtered(
                lambda _r: _r.from_date < self.start_date <= _r.to_date)
            self.env['mrp.timetracking.workorder'].search([('workorder_id', '=', self.workorder_id.id),
                                                           ('period_id', '=', period_id.id)]).write({'is_closed': True})

    def mixed_tracking_restrict_btn(self):
        self.mixed_tracking_btn(True)

        # Calculator methods
    def build_action(self, view_id=None):
        Block = self.env['hr.productivity.block']
        if not view_id:
            view_id = self.env['ir.model.data'].get_object(
                'aci_estimation', 'mrp_timetracking_mixed_wizard_form_view')

        today = datetime.today()
        week_start = today - timedelta(days=today.weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday
        block_week_ids = {}
        day = week_start
        while day.strftime('%Y-%m-%d') <= week_end.strftime('%Y-%m-%d'):
            block_ids = Block.search(
                [('final_start_date', '>=', day.replace(hour=0, minute=0, second=0, microsecond=1)),
                 ('final_end_date', '<=', day.replace(hour=23, minute=59, second=59, microsecond=1)),
                 ('block_origin', 'in', ('calendar', 'extra')),
                 ('block_type', '=', 'active'),
                 ('warehouse_id', '=', self.timetracking_id.warehouse_id.id),
                 ('employee_id', '=', self.workcenter_id.employee_id.id)])
            block_week_ids.update({day.weekday(): block_ids.ids})
            day = day + timedelta(days=1)
        return {
            'name': 'Register Activity//small',
            'res_model': 'mrp.timetracking.mixed.wizard',
            'type': 'ir.actions.act_window',
            'view_id': view_id.id,
            'view_mode': 'form',
            'target': 'new',
            'res_id': self.id
        }

    def show_calculator(self, model_name, field_name, res_id, res_value, mode):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Calculator//small',
            'res_model': 'mrp.estimation.calculator',
            'target': 'new',
            'aci_size': 'small',
            'context': {'default_model_name': model_name,
                        'default_field_name': field_name,
                        'default_res_id': res_id,
                        'default_mode': mode,
                        'default_float_result': res_value,
                        'default_int_result': res_value,
                        'return_action': self.build_action()}
        }

    def show_duration_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'duration', self.id, self.duration, 'float')

    def show_worked_duration_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'worked_duration', self.id, self.worked_duration, 'float')

    def show_qty_operators_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'qty_operators', self.id, self.qty_operators, 'integer')

    def show_qty_progress_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'qty_progress', self.id, self.qty_progress, 'float')

    def show_progress_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'progress', self.id, self.progress, 'integer')

    def show_wo_step_progress_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'wo_step_progress', self.id, self.wo_step_progress, 'integer')

    def show_wo_step_qty_progress_calculator_btn(self, context=None):
        return self.show_calculator('mrp.timetracking.mixed.wizard', 'wo_step_qty_progress', self.id, self.wo_step_qty_progress,
                                    'float')

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
                        'default_model_name': 'mrp.timetracking.mixed.wizard',
                        'default_timetracking_id': self.timetracking_id.id,
                        'default_res_id': self.id,
                        'default_origin_input_type': self.input_type,
                        'return_action': self.build_action()}
        }

    def show_progress_step_btn(self, context=None):
        return self.show_step_btn('progress', 'progress')

    def show_qty_progress_step_btn(self, context=None):
        return self.show_step_btn('qty', 'qty_progress')


class MrpTimetrackingMixedRestrictionWizard(models.TransientModel):
    _name = 'mrp.timetracking.mixed.restriction.wizard'
    _description = 'mrp.timetracking.mixed.restriction.wizard'

    release_restriction = fields.Boolean(default=False)
    tracking_id = fields.Many2one('mrp.timetracking.mixed.wizard')
    activity_id = fields.Many2one('mail.activity')
    res_id = fields.Char(compute='_compute_res_id')
    product_id = fields.Many2one(related='activity_id.product_id', string='Activity')
    workcenter_id = fields.Many2one(related='activity_id.workcenter_id', string='Workcenter')
    summary = fields.Char(related='activity_id.summary')

    @api.depends('activity_id')
    def _compute_res_id(self):
        for r in self:
            r.res_id = self.env[r.activity_id.res_model].browse([r.activity_id.res_id]).name

