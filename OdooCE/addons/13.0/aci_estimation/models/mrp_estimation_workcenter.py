from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
from odoo.http import request
import datetime
from datetime import timedelta

class MrpEstimationWorkcenter(models.Model):
    _name = 'mrp.estimation.workcenter'
    _description = 'mrp.estimation.workcenter'
    _order = 'workcenter_id'
    _rec_name = 'workcenter_id'

    workcenter_id = fields.Many2one('mrp.workcenter', ondelete='cascade')
    workcenter_code = fields.Char('Workcenter Code', compute='_compute_workcenter_code')
    employee_id = fields.Many2one(related='workcenter_id.employee_id', readonly=True)
    block_id = fields.Many2one('hr.productivity.block', ondelete='cascade',
                               compute='_compute_productivity_block', store=True)
    final_start_date = fields.Datetime('Start Activity', related='block_id.final_start_date')
    final_end_date = fields.Datetime('End Activity', related='block_id.final_end_date')
    block_type = fields.Selection('Block Type', related='block_id.block_type')
    block_origin = fields.Selection('Block Type', related='block_id.block_origin')
    do_tracking = fields.Boolean(default=True)
    on_extra_block = fields.Boolean(compute='_compute_extra_block')
    attendance_block_id = fields.Many2one('hr.zk.device.block', compute='_compute_attendance_block')
    attendance_block_start_date = fields.Datetime('Attendance Start', related='attendance_block_id.date_start')
    on_approved_incidence = fields.Boolean(compute='_compute_incidence')
    on_extra_time = fields.Boolean(compute='_compute_extra_time')
    missing_incidence = fields.Boolean(compute='_compute_missing_incidence')
    contract_id = fields.Many2one(related='workcenter_id.contract_id', readonly=True, store=True)
    department_id = fields.Many2one(related='contract_id.department_id', readonly=True, store=True)
    contract_tolerance = fields.Selection(related='contract_id.tolerance')
    has_contract = fields.Boolean(compute='_compute_has_contract')
    active_on_period = fields.Boolean(compute='_compute_active_on')
    has_estimation = fields.Boolean(compute='_compute_has_estimation')
    number_estimation = fields.Integer(compute='_compute_has_estimation', string='No. Estimation')
    is_supervisor = fields.Boolean(compute='_compute_supervised', store=True, compute_sudo=True)
    supervised_count = fields.Integer(compute='_compute_supervised', compute_sudo=True)
    activity_count = fields.Integer(compute='_compute_supervised', compute_sudo=True)
    on_calendar = fields.Boolean(compute='_compute_calendar_state')

    @api.depends('workcenter_id', 'employee_id')
    def _compute_workcenter_code(self):
        for r in self:
            r.workcenter_code = '{}{}'.format(r.workcenter_id.code, ' ({})'.format(r.employee_id.code)
                if r.employee_id.code else '')

    @api.depends('employee_id.block_ids')
    def _compute_productivity_block(self):
        date_now = datetime.datetime.now()
        block = self.env['hr.productivity.block']

        for r in self:
            # ToDo. Limit the search
            block_ids = block.search([('employee_id', '=', r.employee_id.id)], order='final_start_date')
            block_id = None
            for block in block_ids:
                start = block.final_start_date
                end = block.final_end_date
                if start <= date_now <= end:
                    block_id = block.id
                    break
            r.block_id = block_id

    @api.depends('contract_tolerance', 'block_id', 'employee_id')
    def _compute_extra_block(self):
        date_now = datetime.datetime.now()
        block = self.env['hr.productivity.block']
        for _id in self:
            block_ids = block.search([('employee_id', '=', _id.employee_id.id),
                                      ('block_origin', '=', 'extra')], order='final_start_date')
            on_extra_block = False
            for block in block_ids:
                start = block.final_start_date
                end = block.final_end_date
                if start <= date_now <= end:
                    on_extra_block = True
                    break
            _id.on_extra_block = on_extra_block

    @api.depends('employee_id')
    def _compute_attendance_block(self):
        for r in self:
            att_block = self.env['hr.zk.device.block'].search([('employee_id', '=', r.employee_id.id),
                                                               ('date_end', '=', None),
                                                               ('date_start', '<=',
                                                                datetime.datetime.now().strftime(
                                                                    DEFAULT_SERVER_DATETIME_FORMAT))])
            r.attendance_block_id = att_block.id if len(att_block) == 1 else None

    @api.depends('employee_id')
    def _compute_incidence(self):
        date_now = datetime.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        for r in self:
            incidence_id = self.env['attendance.incidence'].search([('employee_id', '=', r.employee_id.id),
                                                                    ('check_in', '<=', date_now),
                                                                    ('check_out', '>=', date_now),
                                                                    ('state', '=', 'approved')])
            r.on_approved_incidence = True if incidence_id else False

    @api.depends('employee_id')
    def _compute_extra_time(self):
        date_now = datetime.datetime.now()
        for r in self:

            if r.workcenter_id.resource_calendar_id:
                tz_check_in = self.env['time.tracking.actions'].get_tz_datetime(date_now, r.employee_id.user_id)
                check_in_hour = self.env['time.tracking.actions'].get_float_hour(tz_check_in)
                attendance_ids = r.workcenter_id.resource_calendar_id.attendance_ids \
                    .filtered(lambda s: int(s.dayofweek) == int(tz_check_in.weekday()) and s.hour_to > check_in_hour)
                r.on_extra_time = False if attendance_ids else True
            else:
                r.on_extra_time = None

    @api.depends('employee_id')
    def _compute_missing_incidence(self):
        for r in self:
            incidence_block_id = self.env['hr.productivity.block'].search([('employee_id', '=', r.employee_id.id),
                                                                           ('block_type', '=', 'inactive'),
                                                                           ('block_origin', '=', 'incidence'),
                                                                           ('incidence_id', '=', None)])

            r.missing_incidence = True if incidence_block_id else False

    @api.depends('contract_id')
    def _compute_has_contract(self):
        for r in self:
            r.has_contract = True if r.contract_id else False

    @api.depends('workcenter_id')
    def _compute_active_on(self):
        for r in self:
            current_period = r.workcenter_id.period_group_id.period_ids. \
                filtered(lambda _r: _r.from_date < datetime.datetime.now() <= _r.to_date)
            timetracking_ids = self.env['mrp.timetracking'].search([('workcenter_id', '=', r.workcenter_id.id),
                                                                    ('period_id', '=', current_period.id),
                                                                    ('production_id.state', 'not in',
                                                                     ['done', 'cancel'])])
            r.active_on_period = True if timetracking_ids else False

    @api.depends('workcenter_id')
    def _compute_has_estimation(self):
        Estimation = self.env['mrp.estimation']

        for r in self:
            current_period = r.workcenter_id.period_group_id.period_ids. \
                filtered(lambda _r: _r.from_date < datetime.datetime.now() <= _r.to_date)

            estimation = Estimation.search([('period_id', '=', current_period.id),
                                            ('workcenter_id', '=', r.workcenter_id.id)])

            r.has_estimation = True if estimation else False
            r.number_estimation = len(estimation.ids)

    @api.depends('active_on_period')
    def _compute_supervised(self):
        for r in self:
            if r.workcenter_id.employee_id:
                workcenter_ids = self.env['mrp.production'].\
                    search([('supervisor_ids', 'in', r.workcenter_id.employee_id.id)]).workorder_ids.mapped('resource_id').ids
            else:
                workcenter_ids = []
            r.supervised_count = len(workcenter_ids)
            r.is_supervisor = True if len(workcenter_ids) > 0 else False
            r.activity_count = len(self.env['mrp.timetracking'].search([('workcenter_id', '=', r.workcenter_id.id)]).ids)

    @api.depends('employee_id', 'block_id')
    def _compute_calendar_state(self):
        date_now = datetime.datetime.now()
        for r in self:
            state = False
            if r.workcenter_id.resource_calendar_id.attendance_ids.filtered(
                    lambda x: int(x.dayofweek) == int(date_now.weekday())):
                first = 24
                last = 0
                for attendance_id in r.workcenter_id.resource_calendar_id.attendance_ids.filtered(
                        lambda x: int(x.dayofweek) == int(date_now.weekday())):
                    if attendance_id.hour_from < first:
                        first = attendance_id.hour_from
                    if attendance_id.hour_to > last:
                        last = attendance_id.hour_to
                from_hour = int('{0:02.0f}'.format(*divmod(first * 60, 60)))
                from_minutes = int('{1:02.0f}'.format(*divmod(first * 60, 60)))
                to_hour = int('{0:02.0f}'.format(*divmod(last * 60, 60)))
                to_minutes = int('{1:02.0f}'.format(*divmod(last * 60, 60)))

                day_start = date_now.replace(hour=from_hour, minute=from_minutes, second=0)
                day_end = date_now.replace(hour=to_hour, minute=to_minutes, second=0)
                utc_day_start = self.env['time.tracking.actions'].remove_tz_datetime(day_start, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                utc_day_end = self.env['time.tracking.actions'].remove_tz_datetime(day_end, self.env.user).strftime(DEFAULT_SERVER_DATETIME_FORMAT)
                if utc_day_start <= str(date_now) <= utc_day_end:
                    state = True
            r.on_calendar = state

    def button_tracking_log(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_timeline')
        step_ids = self.env['mrp.workcenter.productivity'].search([('resource_id', 'in', [self.workcenter_id.id]),
                                                                   ('tracking_origin', '=', 'step')]).ids
        workorder_ids = self.env['mrp.workcenter.productivity'].search([('resource_id', 'in', [self.workcenter_id.id]),
                                                                        ('tracking_origin', '=', 'workorder')]).ids
        _ids = step_ids + workorder_ids
        action = {
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree'), (view_id.id, 'timeline')],
            'view_mode': 'form,timeline',
            'name': 'Tracking Log',
            'res_model': 'mrp.workcenter.productivity',
            'target': 'current',
            'clear_breadcrumbs': True,
            'domain': [('id', 'in', _ids)]
        }
        return action

    def button_leaves(self):
        action = {
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree')],
            'view_mode': 'form,timeline',
            'name': 'Leaves',
            'res_model': 'attendance.incidence',
            'target': 'current',
            'clear_breadcrumbs': True,
            'context': {'wo_wc': [self.workcenter_id.id],
                        'wo_supervised_wc': [self.workcenter_id.id]},
            'domain': [('id', 'in', self.env['attendance.incidence'].search([('employee_id', '=', self.workcenter_id.employee_id.id)]).ids)]
        }
        return action

    def button_blocks(self):
        tz_today = self.env['time.tracking.actions'].get_tz_datetime(datetime.datetime.now(), self.env.user)
        day_start = tz_today.replace(hour=0, minute=0, second=0)
        day_end = tz_today.replace(hour=23, minute=59, second=59)
        day_start = self.env['time.tracking.actions'].remove_tz_datetime(day_start, self.env.user)
        day_end = self.env['time.tracking.actions'].remove_tz_datetime(day_end, self.env.user)
        ids = self.env['hr.productivity.block'].search([('employee_id', '=', self.employee_id.id),
                                                        ('final_start_date', '>=', day_start),
                                                        ('final_start_date', '<=', day_end)
                                                        ]).ids
        blocks = self.env['hr.productivity.block'].search([('employee_id', '=', self.employee_id.id)])
        view_id = self.env['ir.model.data'].get_object('aci_estimation', 'hr_productivity_block_timeline')
        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_id.id, 'timeline'), (False, 'tree')],
            'view_mode': 'form',
            'name': 'Productivity Blocks',
            'res_model': 'hr.productivity.block',
            'target': 'current',
            'clear_breadcrumbs': True,
            'domain': [('id', 'in', ids)],
        }
        return action

    def button_start_activity_estimation(self):
        if not self.on_calendar and self.contract_id.tolerance == 'restrictive':
            raise ValidationError(_('Warning! You are outside your calendar schedule'))
        elif not self.on_calendar:
            self.button_start_extra_activity()
        else:
            self.env['hr.productivity.block'].start_activity([self.workcenter_id.id])

    def button_end_activity_estimation(self):
        if not self.on_calendar:
            self.button_end_extra_activity()
        else:
            self.env['hr.productivity.block'].end_activity([self.workcenter_id.id])

    def button_timeoff(self):
        block_ids = self.env['hr.productivity.block'].search([('employee_id', '=', self.workcenter_id.employee_id.id),
                                                              ('block_origin', '=', 'timeoff')])
        block_id = None
        for _ids in block_ids:
            _date = self.env['time.tracking.actions'].get_tz_datetime(_ids.final_start_date, self.env.user)
            if _date.strftime("%Y-%m-%d") == datetime.datetime.now().strftime("%Y-%m-%d"):
                block_id = _ids.id
                break

        action = {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'Time Off',
            'res_model': 'hr.productivity.block.timeoff',
            'target': 'new',
            'context': {'default_employee_id': self.workcenter_id.employee_id.id,
                        'default_date': datetime.datetime.now(),
                        'default_block_id': block_id}
        }
        return action

    def button_start_extra_activity(self):
        date_now = datetime.datetime.now()
        resource_calendar_id = self.workcenter_id.resource_calendar_id
        if resource_calendar_id and self.contract_id:
            if self.on_calendar:
                raise ValidationError(_("{} is on his calendar working time".format(self.employee_id.name)))
            tz_check_in = self.env['time.tracking.actions'].get_tz_datetime(date_now, self.employee_id.user_id)
            if self.contract_id.tolerance == 'open':
                end = tz_check_in.replace(hour=23, minute=59, second=59)
            else:
                attendance_ids = resource_calendar_id.attendance_ids \
                    .filtered(lambda r: int(r.dayofweek) == int(tz_check_in.weekday())).sorted(lambda r: r.hour_to,
                                                                                               reverse=True)
                hour = int('{0:02.0f}'.format(*divmod(attendance_ids[0].hour_to * 60, 60)))
                minutes = int('{1:02.0f}'.format(*divmod(attendance_ids[0].hour_to * 60, 60)))
                hour_to = tz_check_in.replace(hour=hour, minute=minutes, second=0)
                end = hour_to + timedelta(minutes=self.contract_id.tolerance_time)

            end_day = self.env['time.tracking.actions'].remove_tz_datetime(end, self.employee_id.user_id)
            incidence_id = self.env['attendance.incidence'].create({'check_in': date_now,
                                                                    'check_out': end_day,
                                                                    'employee_id': self.employee_id.id,
                                                                    'name': 'Work Out of Schedule',
                                                                    'productivity_block': False,
                                                                    'type_incidence': 'work_out_schedule'})
            self.env['hr.productivity.block'].create({'start_date': date_now,
                                                      'end_date': end_day,
                                                      'employee_id': self.employee_id.id,
                                                      'resource_calendar_attendance_id': resource_calendar_id.id,
                                                      'block_type': 'active',
                                                      'block_origin': 'extra',
                                                      'incidence_id': incidence_id.id})

    def button_end_extra_activity(self):
        date_now = datetime.datetime.now()
        block_ids = self.env['hr.productivity.block'].search([('employee_id', '=', self.employee_id.id),
                                                              ('block_origin', '=', 'extra')], order='final_start_date')
        block_id = None
        for block in block_ids:
            start = block.final_start_date
            end = block.final_end_date
            if start <= date_now <= end:
                block_id = block
                break
        if block_id:
            block_id.write({'end_date': date_now})
            block_id.incidence_id.end_date = date_now

    def button_end_day(self):
        action = {
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'view_mode': 'form',
            'name': 'End Day',
            'res_model': 'mrp.timetracking.wizard',
            'target': 'new',
            'context': {'default_employee_id': self.workcenter_id.employee_id.id,
                        'default_workcenter_id': self.workcenter_id.id}
        }
        return action

    def button_missing_incidence(self):
        ids = self.env['hr.productivity.block'].search([('employee_id', '=', self.employee_id.id),
                                                        ('incidence_id', '=', None),
                                                        ('block_type', '=', 'inactive'),
                                                        ('block_origin', '=', 'incidence')]).ids
        view_id = self.env['ir.model.data'].get_object('aci_estimation', 'hr_productivity_block_timeline')
        action = {
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree'), (view_id.id, 'timeline')],
            'view_mode': 'form',
            'name': 'Productivity Blocks',
            'res_model': 'hr.productivity.block',
            'target': 'current',
            'clear_breadcrumbs': True,
            'domain': [('id', 'in', ids)]
        }
        return action

    def show_assign_section_btn(self):
        parent_workcenter_id = self.env.context.get('parent_workcenter_id')
        args = [('workcenter_id', '=', self.workcenter_id.id)]
        if parent_workcenter_id:
            workcenter_id = self.env['mrp.workcenter'].browse([parent_workcenter_id])
            if workcenter_id:
                if self.workcenter_id.employee_id.id not in workcenter_id.employee_id.child_ids.ids:
                    supervised_mo_ids = []
                    for production_id in self.env['mrp.production'].search([('state', 'not in', ['done', 'cancel'])]):
                        if workcenter_id.employee_id.id in production_id.supervisor_ids.ids:
                            supervised_mo_ids.append(production_id.id)
                    args.append(('production_id', 'in', supervised_mo_ids))
        timetracking_ids = self.env['mrp.timetracking'].search(args)
        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'name': 'Activity',
            'res_model': 'mrp.timetracking',
            'target': 'current',
            'domain': [('id', 'in', timetracking_ids.ids)],
            "context": {'search_default_active_stage': 1}
        }

    def button_selection_start_estimation(self, context=None):
        context = self.env.context
        workcenter_ids = self.browse(context.get('active_ids'))
        self.env['hr.productivity.block'].start_activity(
            workcenter_ids.filtered(lambda r: r.do_tracking is True).mapped('workcenter_id').ids)

    def button_selection_start_special_estimation(self, context=None):
        context = self.env.context
        workcenter_ids = self.browse(context.get('active_ids'))
        self.env['hr.productivity.block'].start_activity(
            workcenter_ids.filtered(lambda r: r.do_tracking is True).mapped('workcenter_id').ids)

    def button_selection_end_estimation(self, context=None):
        context = self.env.context
        workcenter_ids = self.browse(context.get('active_ids'))
        self.env['hr.productivity.block'].end_activity(
            workcenter_ids.filtered(lambda r: r.do_tracking is True).mapped('workcenter_id').ids)

    def button_estimate_block(self, context=None):
        return {
            'type': 'ir.actions.act_window',
            'views': [(False, 'tree'), (False, 'form')],
            'view_mode': 'tree',
            'name': 'Estimations',
            'res_model': 'mrp.estimation',
            'target': 'current',
            'context': {'default_workcenter_id': self.workcenter_id.id,
                        'search_default_filter_active_estimation': 1},
            'domain': [('workcenter_id', '=', self.workcenter_id.id)]
        }

    def button_supervised(self):
        workcenter_ids = self.env['mrp.production']. \
            search([('supervisor_ids', 'in', self.employee_id.id)]).workorder_ids.mapped('resource_id').ids
        est_workcenter_ids = self.env['mrp.estimation.workcenter'].search([('workcenter_id', 'in', workcenter_ids)])
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_workcenter_baseline_tree_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Workcenters',
            'views': [(view_id.id, 'tree')],
            'res_model': 'mrp.estimation.workcenter',
            'domain': [('id', 'in', est_workcenter_ids.ids)],
            'target': 'current'
        }

class MrpTimetrackingEstimationProductivity(models.TransientModel):
    _name = 'mrp.estimation.productivity'
    _description = 'mrp.estimation.productivity'

class MrpTimetrackingEstimation(models.Model):
    _name = 'mrp.estimation'
    _description = 'mrp.estimation'
    _order = 'period_id, workcenter_id, estimation_type, day'

    can_create_block = fields.Boolean(compute='_compute_can_create_block')
    warehouse_id = fields.Many2one('stock.warehouse')
    block_ids = fields.Many2many('hr.productivity.block', store=True)
    timetracking_ids = fields.Many2many('mrp.timetracking')
    productivity_ids = fields.Many2many('mrp.workcenter.productivity')
    cost_productivity_ids = fields.One2many('mrp.workcenter.productivity', 'estimation_id')
    analytic_line_ids = fields.One2many('account.analytic.line', 'estimation_id')
    estimation_end = fields.Datetime(compute='_compute_estimation_end')
    workcenter_id = fields.Many2one('mrp.workcenter')
    workcenter_code = fields.Char(compute='_compute_workcenter_code')
    workcenter_role = fields.Selection(related='workcenter_id.workcenter_role', readonly=False)
    set_operators = fields.Boolean(related='workcenter_id.set_operators', readonly=False)
    employee_id = fields.Many2one(related='workcenter_id.employee_id')
    contract_id = fields.Many2one('hr.contract', compute='_compute_contract', store=True)
    department_id = fields.Many2one(related='contract_id.department_id', readonly=True, store=True)
    period_id = fields.Many2one('payment.period', ondelete='restrict')
    period_group_id = fields.Many2one('payment.period.group', string='Period Group')
    start_period = fields.Datetime(related='period_id.from_date', store=True)
    end_period = fields.Datetime(related='period_id.to_date')
    duration = fields.Float(compute='_compute_duration', string="Blocks")
    expected_duration = fields.Float(compute='_compute_expected_duration', string="Expected(min)")
    periodic_count = fields.Integer(compute='_compute_periodic_count')
    estimated_duration = fields.Float(compute='_compute_estimated_duration', string="Estimated(min)")
    available_duration = fields.Float(compute='_compute_available_duration', string="Available(min)")
    duration_hours = fields.Char(compute='_compute_hours', string="Blocks")
    expected_duration_hours = fields.Char(compute='_compute_hours', string="Expected")
    estimated_duration_hours = fields.Char(compute='_compute_hours', string="Estimated")
    # approved_estimated_duration = fields.Float(compute='_compute_estimated_duration', string="Approved(min)")
    # approved_estimated_duration_hours = fields.Char(compute='_compute_hours', string="Approved")
    approved_available_duration = fields.Float(compute='_compute_available_duration', string="Final Available Minutes")
    period_status = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Open'),
        ('waiting_approval', 'Closed'),
        ('payable', 'Payable'),
        ('paid', 'Paid'),
        ('canceled', 'Canceled')], default='draft')
    estimation_type = fields.Selection([('daily', 'Daily'), ('period', 'Period')], default='daily')
    day = fields.Date()
    parent_id = fields.Many2one('mrp.estimation')
    daily_estimation_ids = fields.One2many('mrp.estimation', 'parent_id')
    daily_count = fields.Integer(compute='_compute_hours', string="D.Count")
    cost_count = fields.Integer(compute='_compute_cost_count', string="C.Count")
    active_on_period = fields.Boolean(compute='_compute_active_on')
    # is_closed = fields.Boolean(default=False)
    has_daily = fields.Boolean(compute='_compute_has_daily')
    crew_logged = fields.Boolean(compute='_compute_crew_logged')
    approve_employee_id = fields.Many2one('hr.employee', string='Approved by')
    supervisor_employee_id = fields.Many2one('hr.employee', string='Supervised by')

    def name_get(self):
        result = []
        for r in self:
            estimation_type = '' if r.estimation_type == 'period' else '[{}]'.format(r.estimation_type)
            result.append((r.id, '{} {} {}.{}'.format(r.warehouse_id.code, estimation_type, r.period_id.name, r.workcenter_id.name)))
        return result

    def write(self, vals):
        res = super(MrpTimetrackingEstimation, self).write(vals)
        if 'status' in vals.keys():
            for _id in self:
                if _id.available_duration < 0 and vals.get('status') in ['confirmed', 'approved']:
                    raise ValidationError('The estimated duration is bigger than the activity blocks duration')
        if 'period_status' in vals.keys():
            for _id in self:
                if _id.has_daily:
                    _id.daily_estimation_ids.write({'period_status': vals.get('period_status')})
        return res

    @api.depends('workcenter_id', 'employee_id')
    def _compute_workcenter_code(self):
        for r in self:
            r.workcenter_code = '{}{}'.format(r.workcenter_id.code, ' ({})'.format(r.employee_id.code)
                if r.employee_id.code else '')

    @api.depends('employee_id.block_ids')
    def _compute_can_create_block(self):
        for r in self:
            if r.duration == 0 and r.estimation_type == 'daily':
                block_ids = self.env['hr.productivity.block'].search([('employee_id', '=', r.employee_id.id),
                                                                      ('warehouse_id', '=', r.warehouse_id.id),
                                                                      ('duration', '>', 0)], order='final_end_date DESC')
                if block_ids:
                    last_block_day = block_ids[0].final_end_date.strftime('%Y-%m-%d')
                    if last_block_day <= r.day.strftime('%Y-%m-%d') <= datetime.datetime.now().strftime('%Y-%m-%d'):
                        can_create_block = True
                    else:
                        can_create_block = False
                else:
                    can_create_block = True

                if self.env.user.block_creation == 'period':
                    current_period = r.period_group_id.period_ids.filtered(
                        lambda _r: _r.from_date < datetime.datetime.now() <= _r.to_date)
                    to_date = self.env['time.tracking.actions'].get_tz_datetime(r.end_period, self.env.user)
                    from_date = self.env['time.tracking.actions'].get_tz_datetime(r.start_period, self.env.user)
                    valid_days = []
                    wanted_days = r.period_group_id.tracking_window or 1
                    calendar_id = r.workcenter_id.resource_calendar_id
                    while to_date.strftime('%Y-%m-%d') >= from_date.strftime('%Y-%m-%d'):
                        if wanted_days > 0 and calendar_id.attendance_ids.filtered(lambda r: r.dayofweek == str(to_date.weekday())):
                            valid_days.append(to_date.strftime('%Y-%m-%d'))
                            wanted_days -= 1
                        to_date = to_date - timedelta(days=1)
                    can_create_block = True if r.day.strftime('%Y-%m-%d') in valid_days and r.period_id.id == current_period.id else False

                if r.day and r.day.strftime('%Y-%m-%d') == datetime.datetime.now().strftime('%Y-%m-%d'):
                    can_create_block = True

            else:
                can_create_block = False
            r.can_create_block = can_create_block

    @api.depends('block_ids')
    def _compute_estimation_end(self):
        for r in self:
            if r.block_ids:
                estimation_end = r.block_ids.sorted(key=lambda y: y.final_start_date,reverse=True)[0].final_end_date
            else:
                estimation_end = None
            r.estimation_end = estimation_end

    @api.depends('employee_id')
    def _compute_contract(self):
        for _id in self:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', _id.employee_id.id),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            _id.contract_id = contract_id.id if contract_id else None

    @api.depends('block_ids.duration')
    def _compute_duration(self):
        for r in self:
            r.duration = sum(block_id.duration for block_id in r.block_ids)

    @api.depends('timetracking_ids', 'timetracking_ids.real_duration_expected')
    def _compute_expected_duration(self):
        for r in self:
            r.expected_duration = sum(timetracking_id.real_duration_expected for timetracking_id in r.timetracking_ids
                                      if timetracking_id.baseline_id.type != 'periodic' and
                                      timetracking_id.available is True and
                                      timetracking_id.timetracking_active is True and
                                      timetracking_id.tracking_origin == 'workorder')

    @api.depends('timetracking_ids', 'timetracking_ids.real_duration_expected')
    def _compute_periodic_count(self):
        for r in self:
            r.periodic_count = len([timetracking_id.id for timetracking_id in r.timetracking_ids
                                      if timetracking_id.baseline_id.type == 'periodic' and
                                     timetracking_id.available is True and
                                     timetracking_id.timetracking_active is True and
                                     timetracking_id.tracking_origin == 'workorder'])

    @api.depends('productivity_ids', 'productivity_ids.duration')
    def _compute_estimated_duration(self):
        for r in self:
            r.estimated_duration = sum(productivity_id.duration for productivity_id in r.productivity_ids)
            # r.approved_estimated_duration = sum(estimation_id.approved_duration for estimation_id in r.estimation_ids)

    def get_hours_string(self, _date):
        seconds = _date.total_seconds()
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return '{}:{}'.format(h, m if m >= 10 else '0{}'.format(m))

    @api.depends('duration', 'expected_duration', 'estimated_duration', 'daily_estimation_ids')
    def _compute_hours(self):
        for r in self:
            r.duration_hours = self.get_hours_string(timedelta(minutes=r.duration))
            r.expected_duration_hours = self.get_hours_string(timedelta(minutes=r.expected_duration))
            r.estimated_duration_hours = self.get_hours_string(timedelta(minutes=r.estimated_duration))
            # r.approved_estimated_duration_hours = self.get_hours_string(timedelta(minutes=r.approved_estimated_duration))
            r.daily_count = len(r.daily_estimation_ids.ids)

    @api.depends('estimated_duration', 'duration')
    def _compute_available_duration(self):
        for r in self:
            r.available_duration = r.duration - r.estimated_duration
            # r.approved_available_duration = r.duration - r.approved_estimated_duration

    @api.depends('cost_productivity_ids')
    def _compute_cost_count(self):
        for r in self:
            r.cost_count = len(r.cost_productivity_ids.filtered(lambda y: y.qty_status != 'pending'))

    @api.depends('workcenter_id')
    def _compute_active_on(self):
        for r in self:
            current_period = r.workcenter_id.period_group_id.period_ids. \
                filtered(lambda _r: _r.from_date < datetime.datetime.now() <= _r.to_date)
            r.active_on_period = True if r.period_id.id == current_period.id else False

    @api.depends('daily_estimation_ids')
    def _compute_has_daily(self):
        for r in self:
            r.has_daily = True if r.daily_estimation_ids else False

    @api.depends('workcenter_id.employee_ids')
    def _compute_crew_logged(self):
        Block = self.env['hr.productivity.block']
        for r in self:
            if not r.day:
                has_activity_block = [False]
            else:
                has_activity_block = []
                for employee_id in r.workcenter_id.employee_ids:
                    start = datetime.datetime.combine(r.day, datetime.datetime.min.time()).replace(hour=0, minute=0,
                                                                                    second=0,
                                                                                    microsecond=0)
                    end = datetime.datetime.combine(r.day, datetime.datetime.min.time()).replace(hour=23, minute=59,
                                                                                  second=59,
                                                                                  microsecond=0)

                    has_activity_block.append(True if Block.search([('employee_id', '=', employee_id.id),
                                                                    ('final_start_date', '>=', start),
                                                                    ('final_start_date', '<=', end)]) else False)
            r.crew_logged = True if True in has_activity_block else False

    @api.model
    def _create_estimation(self):
        """ Called once a day by a cron.
        """
        todo_stage_id = self.env['time.tracking.actions'].get_stage_id('ToDo')
        finished_stage_id = self.env['time.tracking.actions'].get_stage_id('Finished')
        # for period_group_id in self.env['payment.period.group'].search([]):
        #     current_period = period_group_id.period_ids.filtered(lambda _r: _r.from_date < datetime.datetime.now() <= _r.to_date)
        #     timetracking_ids = self.env['mrp.timetracking'].search([('period_group_id', '=', period_group_id.id),
        #                                                             ('period_id.global_sequence', '<', current_period.global_sequence),
        #                                                             ('stage_id', '=', todo_stage_id)])
        #     for timetracking_id in timetracking_ids:
        #         if timetracking_id.production_id.type == 'building' and timetracking_id.estimation_qty < timetracking_id.product_qty:
        #             timetracking_id.write({'manual_period_id': current_period.id})
        #         else:
        #             timetracking_id.write({'stage_id': finished_stage_id})

    def show_estimation_end_calculator_btn(self, context=None):
        if self.block_ids:
            return self.block_ids.sorted(key=lambda y: y.final_start_date, reverse=True)[0].show_offset_end_date_calculator_btn()
        return True

    def update_activity_block_btn(self):
        blocks = [('block_type', '=', 'active'),
                  ('employee_id', '=', self.employee_id.id),
                  ('warehouse_id', '=', self.warehouse_id.id)]
        if self.estimation_type == 'daily':
            start = datetime.datetime.strptime('{} 00:00:00'.format(self.day), DEFAULT_SERVER_DATETIME_FORMAT)
            end = datetime.datetime.strptime('{} 23:59:59'.format(self.day), DEFAULT_SERVER_DATETIME_FORMAT)

            tz_start = self.env['time.tracking.actions'].remove_tz_datetime(start, self.env.user)
            tz_end = self.env['time.tracking.actions'].remove_tz_datetime(end, self.env.user)

            blocks.append(('final_start_date', '>=', tz_start))
            blocks.append(('final_start_date', '<=', tz_end))
        else:
            blocks.append(('final_end_date', '>=', self.period_id.from_date))
            blocks.append(('final_end_date', '<=', self.period_id.to_date))
        block_ids = self.env['hr.productivity.block'].search(blocks)
        self.block_ids = [(6, 0, block_ids.ids)]
        self.period_status = 'open'

    def update_estimation_btn(self):
        self.env['mrp.estimation.wizard'].build_estimation(self.period_id.from_date, self.period_id.to_date,
                                                      self.workcenter_id, self.workcenter_id.employee_id,
                                                      self.period_id)

    def create_activity_block_btn(self):
        tz_wanted_date = datetime.datetime.combine(self.day, datetime.datetime.min.time())
        wanted_date = self.env['time.tracking.actions'].remove_tz_datetime(tz_wanted_date, self.env.user)
        self.env['hr.productivity.block'].generate_blocks(wanted_date, None, validate_time=False,
                                                          _employee_id=self.workcenter_id.employee_id,
                                                          warehouse_id=self.warehouse_id.id)
        self.update_activity_block_btn()

    def create_crew_activity_block_btn(self):

        employee_crew_ids = [(0, False, {'employee_id': emp.id}) for emp in self.workcenter_id.employee_ids]
        date_ids = [(0, False, {'block_date': self.day,
                                'name': self.day.strftime('%a %m/%d')})]

        return {
            'name': _('Crew LogIn'),
            'res_model': 'mrp.estimation.crew.wizard',
            'type': 'ir.actions.act_window',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_date_ids': date_ids,
                        'default_employee_crew_ids': employee_crew_ids}
        }

    def create_multiple_activity_block_btn(self, context=None):
        context = self.env.context
        estimation_ids = self.browse(context.get('active_ids'))
        for estimation_id in estimation_ids.filtered(lambda r: r.can_create_block is True):
            tz_wanted_date = datetime.datetime.combine(estimation_id.day, datetime.datetime.min.time())
            wanted_date = self.env['time.tracking.actions'].remove_tz_datetime(tz_wanted_date, self.env.user)

            self.env['hr.productivity.block'].generate_blocks(wanted_date, None, validate_time=False,
                                                              _employee_id=estimation_id.workcenter_id.employee_id,
                                                              warehouse_id=estimation_id.warehouse_id.id)
            estimation_id.update_activity_block_btn()

    def activity_block_btn(self):
        view_id = self.env['ir.model.data'].get_object('aci_estimation', 'hr_productivity_block_tree_view')
        timeline_view_id = self.env['ir.model.data'].get_object('aci_estimation', 'hr_productivity_block_timeline')
        return {
            'name': _('Activity Blocks'),
            'res_model': 'hr.productivity.block',
            'type': 'ir.actions.act_window',
            'views': [(timeline_view_id.id, 'timeline'), (view_id.id, 'tree')],
            'target': 'current',
            'domain': [('id', 'in', self.block_ids.ids)]}

    def planned_tracking_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_tree_view')
        calendar_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_calendar_view')
        if self.estimation_type == 'daily':
            start = self.validate_daily()
            can_input = True if start.strftime('%Y-%m-%d') == self.day.strftime('%Y-%m-%d') else False
        else:
            can_input = True
        return {
            'type': 'ir.actions.act_window',
            'name': 'Planned',
            'views': [(view_id.id, 'tree'), (calendar_view_id.id, 'calendar')],
            'res_model': 'mrp.timetracking',
            'domain': [('id', 'in', self.timetracking_ids.filtered(lambda r: r.baseline_id.type !=
                                                                                           'periodic' and
                                                                                           r.available is True).ids)],
            'target': 'current',
            'context': {'can_input': can_input}
        }

    def validate_daily(self):
        Block = self.env['hr.productivity.block']
        Productivity = self.env['mrp.workcenter.productivity']

        search_args = [('employee_id', '=', self.workcenter_id.employee_id.id),
                       ('block_type', '=', 'active'),
                       ('warehouse_id', '=', self.warehouse_id.id),
                       ('block_origin', 'in', ('calendar', 'extra'))]

        period_start = self.period_id.from_date
        period_end = self.period_id.to_date
        productivity_id = Productivity.search([('employee_id', '=', self.workcenter_id.employee_id.id),
                                               ('warehouse_id', '=', self.warehouse_id.id),
                                               ('final_start_date', '>=', period_start),
                                               ('final_end_date', '<=', period_end)],
                                              order='final_end_date DESC', limit=1)

        if productivity_id:
            search_args.append(('final_start_date', '<=', productivity_id.final_end_date))
            search_args.append(('final_end_date', '>=', productivity_id.final_end_date))
        else:
            search_args.append(('final_start_date', '>=', period_start))
            search_args.append(('final_end_date', '<=', period_end))

        block_id = Block.search(search_args, order='final_start_date ASC', limit=1)

        if not productivity_id and block_id:
            start_date = block_id.final_start_date + timedelta(seconds=1)
        elif productivity_id and not block_id:
            search_args = [('employee_id', '=', self.workcenter_id.employee_id.id),
                           ('block_type', '=', 'active'),
                           ('block_origin', 'in', ('calendar', 'extra')),
                           ('warehouse_id', '=', self.warehouse_id.id),
                           ('final_start_date', '>=', productivity_id.final_end_date),
                           ('final_end_date', '<=', period_end)]
            block_id = Block.search(search_args, order='final_start_date ASC', limit=1)
            if block_id:
                start_date = block_id.final_start_date + timedelta(seconds=1)
        elif productivity_id:
            start_date = productivity_id.final_end_date + timedelta(seconds=1)

        if productivity_id and block_id and productivity_id.final_end_date.replace(microsecond=0) == \
                block_id.final_end_date.replace(microsecond=0):
            search_args = [('employee_id', '=', self.workcenter_id.employee_id.id),
                           ('block_type', '=', 'active'),
                           ('block_origin', 'in', ('calendar', 'extra')),
                           ('warehouse_id', '=', self.warehouse_id.id),
                           ('final_start_date', '>', block_id.final_end_date),
                           ('final_end_date', '<=', period_end)]
            block_id = Block.search(search_args, order='final_start_date ASC', limit=1)
            if block_id:
                start_date = block_id.final_start_date + timedelta(seconds=1)

        if not block_id:
            period_start = self.env['time.tracking.actions'].get_tz_datetime(self.period_id.from_date,
                                                                             self.env.user)
            period_end = self.env['time.tracking.actions'].get_tz_datetime(self.period_id.to_date,
                                                                           self.env.user)
            raise UserError('Could not find a valid activity block for period {} ({} to {})'.format(
                self.period_id.name, period_start.strftime("%m/%d/%Y"), period_end.strftime("%m/%d/%Y")))
        return start_date

    def planned_periodic_tracking_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_tree_view')
        calendar_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_calendar_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activity',
            'views': [(view_id.id, 'tree'), (calendar_view_id.id, 'calendar')],
            'res_model': 'mrp.timetracking',
            'domain': [('id', 'in', self.timetracking_ids.filtered(lambda r: r.baseline_id.type == 'periodic' and
                                                                   r.available is True).ids)],
            'target': 'current'
        }

    def productivity_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_timeline')
        view_tree_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_estimation_tree_view')

        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_tree_id.id, 'tree'), (view_id.id, 'timeline')],
            'view_mode': 'form,timeline',
            'name': 'Tracking Log',
            'res_model': 'mrp.workcenter.productivity',
            'target': 'current',
            'clear_breadcrumbs': True,
            'domain': [('id', 'in', self.productivity_ids.ids)],
            'context': {'base_estimation_id': self.id,
                        'group_by': ['analytic_id']}
        }
        return action

    def daily_estimation_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_daily_tree_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Daily',
            'views': [(view_id.id, 'tree'), (False, 'form')],
            'res_model': 'mrp.estimation',
            'domain': [('id', 'in', self.daily_estimation_ids.ids)],
            'target': 'current'
        }

    def cost_productivity_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_timeline')
        view_tree_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_estimation_cost_tree_view')
        view_pivot_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_estimation_pivot_view')

        action = {
            'type': 'ir.actions.act_window',
            'views': [(view_tree_id.id, 'tree'),
                      (view_pivot_id.id, 'pivot'),
                      (view_id.id, 'timeline')],
            'view_mode': 'form,timeline',
            'name': 'Cost Report',
            'res_model': 'mrp.workcenter.productivity',
            'target': 'current',
            'clear_breadcrumbs': True,
            'domain': [('id', 'in', self.cost_productivity_ids.filtered(lambda r: r.qty_status != 'pending').ids)],
            'context': {'base_estimation_id': self.id,
                        'group_by': ['period_id', 'employee_id', 'analytic_id', 'product_id'],
                        'default_search_current_period': True}
        }
        return action

    def update_planned_btn(self):
        day = datetime.datetime.strptime('{} 00:00:00'.format(self.day), DEFAULT_SERVER_DATETIME_FORMAT) if self.estimation_type == 'daily' else None
        res_ids = self.env['mrp.estimation.wizard'].get_timetracking(day, self.estimation_type, self.workcenter_id, self.period_id, self.warehouse_id)
        self.write({'timetracking_ids': [(6, 0, list(set(res_ids.ids + self.timetracking_ids.ids)))]})

    def update_tracking_btn(self):
        day = datetime.datetime.strptime('{} 00:00:00'.format(self.day), DEFAULT_SERVER_DATETIME_FORMAT) if self.estimation_type == 'daily' else None
        res_ids = self.env['mrp.estimation.wizard'].get_productivity(day, self.estimation_type, self.workcenter_id, self.period_id, self.warehouse_id)
        self.write({'productivity_ids': [(6, 0, list(set(res_ids.ids + self.productivity_ids.ids)))]})

    def show_workorder_tracking_btn(self):
        Timetracking = self.env['mrp.timetracking']
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
                action = Timetracking.build_redirect_action(type='workorder', workcenter_id=workcenter_id,
                                                        period_id=self.period_id.id,
                                                        filter_workcenter_id=self.workcenter_id.id)
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_wo_action').read()[0]
                action['context'] = {'default_tracking_by': 'workorder',
                                     'default_tracking_method': 'building',
                                     'default_period_id': self.period_id.id}
        else:
            action = Timetracking.build_redirect_action(type='workorder', period_id=self.period_id.id,
                                                        filter_workcenter_id=self.workcenter_id.id)
        return action

    def show_step_tracking_btn(self):
        Timetracking = self.env['mrp.timetracking']
        if self.env.user.shared_account:
            if request.session.get('session_workcenter'):
                workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
                action = Timetracking.build_redirect_action(type='step', workcenter_id=workcenter_id,
                                                        period_id=self.period_id.id,
                                                        filter_workcenter_id=self.workcenter_id.id)
            else:
                action = self.env.ref('aci_estimation.mrp_tracking_wo_action').read()[0]
                action['context'] = {'default_tracking_by': 'step',
                                     'default_tracking_method': 'building',
                                     'default_period_id': self.period_id.id}
        else:
            action = Timetracking.build_redirect_action(type='step', period_id=self.period_id.id,
                                                        filter_workcenter_id=self.workcenter_id.id)
        return action

    def set_canceled_btn(self):
        self.period_status = 'canceled'

    def set_open_btn(self):
        self.period_status = 'open'

    def set_waiting_btn(self):
        self.period_status = 'waiting_approval'

    def set_payable_btn(self):
        self.period_status = 'payable'

    def set_paid_btn(self):
        AccountLine = self.env['account.analytic.line']
        cmds = []
        for analytic_id in self.cost_productivity_ids.filtered(lambda r: r.qty_status == 'approved' and r.available is True).mapped('analytic_id'):
            cost_ids = self.cost_productivity_ids.filtered(lambda r: r.analytic_id.id == analytic_id.id)
            amount = sum(cost_ids.mapped('total_cost'))
            if amount > 0:
                cmds.append({'name': '[{}]{}.{}'.format(self.estimation_type, self.period_id.name, self.workcenter_id.name),
                             'account_id': analytic_id.id,
                             'amount': amount * -1,
                             'estimation_id': self.id})
        AccountLine.create(cmds)
        self.period_status = 'paid'


class AccountAnalyticLine(models.Model):
    _inherit = 'account.analytic.line'

    estimation_id = fields.Many2one('mrp.estimation', ondelete='restrict')