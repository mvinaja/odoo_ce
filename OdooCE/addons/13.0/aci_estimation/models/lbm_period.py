# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.http import request
from datetime import timedelta


class LbmPeriod(models.Model):
    _inherit = 'lbm.period'

    baseline_type = fields.Selection(related='scenario_id.baseline_id.type')
    baseline_id = fields.Many2one(related='scenario_id.baseline_id')
    configuration_validated = fields.Boolean(default=False)
    distribution_validated = fields.Boolean(default=False)
    tracking_validated = fields.Boolean(default=False)
    has_workorder = fields.Boolean(compute='_compute_has_workorder')
    lbm_workorder_ids = fields.Many2many('lbm.workorder',
                                         'lbm_period_lbm_workorder_rel', 'lbm_period_id', 'lbm_workorder_id')
    is_closed = fields.Boolean(default=False)
    daily_tracking = fields.Boolean(default=False)

    @api.model
    def create(self, vals):
        res = super(LbmPeriod, self).create(vals)
        res.validate_scenario_btn()
        res.create_distribution_btn()
        return res

    @api.depends('lbm_workorder_ids', 'is_closed')
    def _compute_has_workorder(self):
        for r in self:
            r.has_workorder = True if r.lbm_workorder_ids and r.is_closed is False else False

    def get_datetime_calendar(self, calendar_id, _date, day_condition='prev'):
        _date = self.env['time.tracking.actions'].get_tz_datetime(_date, self.env.user)
        weekday = _date.weekday()
        schedule = None
        _days = -1
        while not schedule:
            schedule = calendar_id.attendance_ids.filtered(lambda r: r.dayofweek == str(weekday))
            if day_condition == 'prev':
                weekday = weekday - 1 if weekday != 0 else 6
            else:
                weekday = weekday + 1 if weekday != 6 else 0
            _days += 1

        if day_condition == 'prev':
            _date = _date - timedelta(days=_days)
        else:
            _date = _date + timedelta(days=_days)

        if _days >= 1 and day_condition == 'prev':
            _date = _date.replace(hour=23, minute=59, second=59)
        elif _days >= 1:
            _date = _date.replace(hour=0, minute=0, second=0)
        date_start = []
        date_end = []
        valid = False
        for att in schedule:
            from_hour = int('{0:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
            from_minutes = int('{1:02.0f}'.format(*divmod(att.hour_from * 60, 60)))
            to_hour = int('{0:02.0f}'.format(*divmod(att.hour_to * 60, 60)))
            to_minutes = int('{1:02.0f}'.format(*divmod(att.hour_to * 60, 60)))
            _start = _date.replace(hour=from_hour, minute=from_minutes, second=0)
            _end = _date.replace(hour=to_hour, minute=to_minutes, second=0)
            if _start < _date < _end:
                valid = True
            date_start.append(_start)
            date_end.append(_end)
        if not valid:
            if max(date_end) < _date:
                _date = max(date_end)
            elif min(date_start) > _date:
                _date = min(date_start)
            else:
                calculated_date = None
                for _start in date_start:
                    if _start <= _date:
                        calculated_date = _date
                _date = calculated_date
        return self.env['time.tracking.actions'].remove_tz_datetime(_date, self.env.user)

    def null_button(self):
        return True

    def change_can_be_planned(self, period_state):
        if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
            raise ValidationError(_('You are not allowed to do this process'))
        TimeTracking = self.env['mrp.timetracking']
        context = self.env.context
        period_ids = self.browse(context.get('active_ids'))
        for period_id in period_ids:
            period_id.is_closed = period_state
            TimeTracking.search([('lbm_period_id', '=', period_id.period_id.id)]).write({'available': not period_state})

    def block_period_btn(self, context=None):
        self.change_can_be_planned(True)

    def open_period_btn(self, context=None):
        self.change_can_be_planned(False)

    def validate_scenario_btn(self):
        if not self.env.user.has_group('aci_estimation.group_estimation_resident'):
            raise ValidationError(_('You are not allowed to do this process'))
        self.configuration_validated = False
        self.distribution_validated = False
        self.tracking_validated = False
        self.update_lbm_workorder()
        production_ids = self.lbm_workorder_ids.mapped('workorder_id').mapped('production_id').filtered(lambda r: r.state not in ('cancel', 'done'))
        error_log = []
        warning_log = []
        # Data Validation
        for production_id in production_ids:
            # Objects to create
            workorder_ids = production_id.mapped('workorder_ids')
            analytic_ids = [production_id.project_id.id]
            error_log, warning_log = self.scenario_id.validate_tracking(workorder_ids, analytic_ids,
                                                                        production_id.type, self.baseline_type,
                                                                        error_log, warning_log)

        if len(error_log) > 0:
            self.tracking_validated = False
            return {
                'name': _('Error'),
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'popup.message',
                'res_id': self.scenario_id._generate_error_message(error_log, warning_log).id,
                'target': 'new'
            }
        self.configuration_validated = True

    def update_lbm_workorder(self):
        if self.baseline_type == 'periodic':
            lbm_workorder_ids = self.scenario_id.lbm_workord_ids
        else:
            lbm_workorder_ids = self.scenario_id.lbm_workord_ids.filtered(
                lambda r: (self.period_id.from_date <= r.date_start <= self.period_id.to_date) or
                          (self.period_id.from_date <= r.date_end <= self.period_id.to_date) or
                          (self.period_id.from_date >= r.date_start and self.period_id.to_date <= r.date_end))
        self.lbm_workorder_ids = [(4, lbm_workorder_id.id) for lbm_workorder_id in lbm_workorder_ids]

    def create_distribution(self):
        DisModel = self.env['mrp.timetracking.workorder']
        field_name = 'tworkorder_ids'
        lbm_workorder_ids = self.lbm_workorder_ids
        lbm_workorder_ids.mapped('workorder_id').confirm_workstep()
        tworkorder_ids = self.env['mrp.timetracking.workorder'].search([
           ('baseline_id', '=', self.scenario_id.baseline_id.id),
           ('start_date', '>=', self.period_start),
           ('start_date', '<=', self.period_end)])
        for tworkorder_id in tworkorder_ids:
            if self.baseline_type == 'periodic':
                lbm_workorder_id = lbm_workorder_ids.filtered(lambda r: r.workorder_id.id == tworkorder_id.workorder_id.id)
            else:
                lbm_workorder_id = lbm_workorder_ids.filtered(lambda r: r.date_end >= self.period_id.from_date
                                                              and r.date_start <= self.period_id.to_date
                                                              and r.workorder_id.id == tworkorder_id.workorder_id.id)
            valid = True if lbm_workorder_id else False
            if not valid and tworkorder_id.period_id == tworkorder_id.ite_period_id:
                if tworkorder_id.executed_progress > 0:
                    tworkorder_id.write({
                           'planned_progress': 0,
                           'planned_qty_progress': 0,
                           'ite_progress': 0,
                           'ite_qty_progress': 0,
                           'can_be_planned': False})
                else:
                    tworkorder_id.unlink()

        for lbm_workorder_id in lbm_workorder_ids:
            workorder_id = lbm_workorder_id.workorder_id
            calendar_id = workorder_id.resource_id.resource_calendar_id
            valid = False
            if self.baseline_type == 'periodic':
                valid = True
            else:
                if lbm_workorder_id.date_end >= self.period_id.from_date and lbm_workorder_id.date_start <= self.period_id.to_date:
                    valid = True

            if valid:
                if self.baseline_type == 'periodic':
                    date_start = self.get_datetime_calendar(calendar_id, self.period_id.from_date, 'next')
                    date_end = self.get_datetime_calendar(calendar_id, self.period_id.to_date)
                else:
                    if lbm_workorder_id.date_start < self.period_id.from_date:
                        date_start = self.get_datetime_calendar(calendar_id, self.period_id.from_date, 'next')
                    else:
                        date_start = lbm_workorder_id.date_start

                    if lbm_workorder_id.date_end > self.period_id.to_date:
                        date_end = self.get_datetime_calendar(calendar_id, self.period_id.to_date)
                    else:
                        date_end = lbm_workorder_id.date_end

                tz_date_start = self.env['time.tracking.actions'].get_tz_datetime(date_start, self.env.user)
                tz_date_end = self.env['time.tracking.actions'].get_tz_datetime(date_end, self.env.user)

                duration = self.scenario_id.get_duration_by_calendar(calendar_id, tz_date_start, tz_date_end)

                tz_date_start = self.env['time.tracking.actions'].get_tz_datetime(
                    workorder_id.date_planned_start, self.env.user)
                tz_date_end = self.env['time.tracking.actions'].get_tz_datetime(
                    workorder_id.date_planned_finished, self.env.user)
                tracking_duration_expected = self.env['lbm.scenario'].get_duration_by_calendar(
                    workorder_id.resource_id.resource_calendar_id,
                    tz_date_start, tz_date_end)
                qty = workorder_id.qty_production if self.baseline_type == 'periodic' else\
                    duration * workorder_id.qty_production / tracking_duration_expected
                progress = 100 if self.baseline_type == 'periodic' else \
                    round(duration * 100 / tracking_duration_expected, 2)

                record_id = DisModel.search([('workorder_id', '=', workorder_id.id),
                                             ('ite_period_id', '=', self.period_id.id)])

                if not record_id:
                    workorder_id.write({field_name: [(0, False, {'workorder_id': workorder_id.id,
                                                                 'period_id': self.period_id.id,
                                                                 'ite_period_id': self.period_id.id,
                                                                 'start_date': date_start,
                                                                 'end_date': date_end,
                                                                 'planned_progress': progress,
                                                                 'planned_qty_progress': qty,
                                                                 'ite_progress': progress,
                                                                 'ite_qty_progress': qty,
                                                                 'lbm_workorder_id': lbm_workorder_id.id,
                                                                 'planned_workcenter_id': workorder_id.resource_id.id,
                                                                 'timetracking_type': workorder_id.timetracking_type if workorder_id.timetracking_type else 'workorder',
                                                                 'duration': duration}
                                                           )]})
                else:
                    record_id.write({
                       'start_date': date_start,
                       'end_date': date_end,
                       'planned_progress': progress,
                       'planned_qty_progress': qty,
                       'lbm_workorder_id': lbm_workorder_id.id,
                       'planned_workcenter_id': workorder_id.resource_id.id,
                       'duration': duration})

    def create_distribution_btn(self):
        if not self.env.user.has_group('aci_estimation.group_estimation_resident'):
            raise ValidationError(_('You are not allowed to do this process'))
        self.distribution_validated = False
        self.tracking_validated = False
        self.create_distribution()
        self.distribution_validated = True

    def compute_period_btn(self, context=None):
        scenario_id = self.env['lbm.scenario'].browse([self.env.context.get('default_scenario_id')])
        if scenario_id:
            dates = scenario_id.baseline_id.production_ids.workorder_ids.timetracking_ids.mapped(
                'date_start')
            dates = sorted(dates)
            if dates:
                period_group_id = scenario_id.baseline_id.group_ids[0]
                first_period = period_group_id.period_ids.filtered(lambda r: r.from_date < dates[0] <= r.to_date)
                last_period = period_group_id.period_ids.filtered(lambda r: r.from_date < dates[-1] <= r.to_date)
                if first_period and last_period:
                    period_ids = period_group_id.period_ids.filtered(lambda r: first_period.global_sequence <= r.global_sequence <= last_period.global_sequence)
                    cmds = []
                    for period_id in period_ids:
                        if not scenario_id.period_ids.filtered(lambda r: r.period_id.id == period_id.id):
                            cmds.append((0, False, {'period_id': period_id.id,
                                                    'period_group': period_group_id.id}))
                    if cmds:
                        scenario_id.period_ids = cmds
                for period_id in scenario_id.period_ids:
                    period_id.validate_scenario_btn()
                    period_id.create_distribution_btn()
                    period_id.process_replanning_btn()
            for period_id in scenario_id.period_ids:
                ite_ids = self.env['mrp.timetracking.workorder'].search([
                    ('baseline_id', '=', period_id.scenario_id.baseline_id.id),
                    ('start_date', '>=', period_id.period_start),
                    ('start_date', '<=', period_id.period_end)])
                if not ite_ids:
                    period_id.unlink()

    def compute_ite_btn(self, context=None):
        if not self.env.user.has_group('aci_estimation.group_estimation_manager'):
            raise ValidationError(_('You are not allowed to do this process'))
        context = self.env.context
        period_ids = self.browse(context.get('active_ids'))
        for period_id in period_ids.filtered(lambda r: r.is_closed is False):
            period_id.validate_scenario_btn()
            period_id.create_distribution_btn()

    def get_ite_ids(self):
        search_args = [('baseline_id', '=', self.scenario_id.baseline_id.id),
                       ('start_date', '>=', self.period_start),
                       ('start_date', '<=', self.period_end)]

        if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
            if request.session.get('session_workcenter'):
                workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
            else:
                workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)],
                                                                  limit=1)
            workcenter_ids, dic_supervised_wc = self.env['mrp.tracking.access'].get_supervised(workcenter_id.id)
            search_args.append(('workcenter_id', 'in', workcenter_ids))
        return self.env['mrp.timetracking.workorder'].search(search_args)

    def show_ite_monitoring_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_workorder_view_pivot')
        _ids = self.get_ite_ids()
        return {'type': 'ir.actions.act_window',
                'name': 'ITE Monitoring',
                'views': [(view_id.id, 'pivot')],
                'res_model': 'mrp.timetracking.workorder',
                'domain': [('id', 'in', _ids.ids if _ids else [])],
                'target': 'current'}

    def show_estim_monitoring_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_workorder_view_pivot_estim')
        _ids = self.get_ite_ids()
        return {'type': 'ir.actions.act_window',
                'name': 'Estimation Monitoring',
                'views': [(view_id.id, 'pivot')],
                'res_model': 'mrp.timetracking.workorder',
                'domain': [('id', 'in', _ids.ids if _ids else [])],
                'target': 'current'}

    def show_wo_monitoring_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workorder_monitoring_pivot_view')
        view_tree_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workorder_monitoring_tree_view')
        return {'type': 'ir.actions.act_window',
                'name': 'WorkOrder Monitoring',
                'views': [(view_id.id, 'pivot'),(view_tree_id.id, 'tree')],
                'res_model': 'mrp.workorder.monitoring',
                'domain': [('period_id', '=', self.period_id.id)],
                'target': 'current'}

    def show_cost_report_btn(self):
        data = {
            'model': self._name,
            'ids': self.ids,
            'form': {
                'period_start_id': self.period_id.id,
                'period_end_id': self.period_id.id,
            },
        }
        return self.env.ref('aci_estimation.cost_estim_report').report_action(self, data=data)

    def show_distribution_btn(self):
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_workorder_view_tree')
        view_gantt_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_workorder_view_gantt')

        _ids = self.get_ite_ids()
        return {'type': 'ir.actions.act_window',
                'name': '{} ITE'.format(self.period_id.name),
                'views': [(view_id.id, 'tree'), (view_gantt_id.id, 'gantt')],
                'res_model': 'mrp.timetracking.workorder',
                'domain': [('id', 'in', _ids.ids if _ids else [])],
                'target': 'current'}

    def send_to_estimation_btn(self, context=None):
        context = self.env.context
        period_ids = self.browse(context.get('active_ids'))
        for period_id in period_ids.filtered(lambda r: r.is_closed is False):
            period_id.process_replanning_btn()

    def create_tracking(self, cmds, rep_id, step_id=None):
        calendar_id = rep_id.workcenter_id.resource_calendar_id
        contract_id = rep_id.workcenter_id.contract_id
        estimation_type = rep_id.workcenter_id.estimation_type
        date_start = rep_id.start_date
        date_end = rep_id.end_date
        workorder_id = rep_id.workorder_id
        workcenter_id = rep_id.workcenter_id
        production_id = rep_id.production_id
        origin = self.baseline_type
        replanning_progress = rep_id.replanning_progress

        if rep_id.production_id.type in ('operational', 'periodic') and contract_id and contract_id.analytic_account_id:
            analytic_id = contract_id.analytic_account_id.id
        else:
            analytic_id = rep_id.analytic_id.id

        # Validate PeriodGroup of workcenter
        if origin in ('building', 'project'):
            period_group_id = workcenter_id.period_group_id
            period_start = workcenter_id.period_group_id.period_ids. \
                filtered(lambda _r: _r.from_date < date_start <= _r.to_date)
            period_end = workcenter_id.period_group_id.period_ids. \
                filtered(lambda _r: _r.from_date < date_end <= _r.to_date)

            period_ids = []
            sequence = period_start.global_sequence
            end_sequence = period_end.global_sequence
            while sequence <= end_sequence:
                period_id = self.env['payment.period'].search([('group_id', '=', period_group_id.id),
                                                               ('global_sequence', '=', sequence)])
                if period_id:
                    period_ids.append(period_id)
                sequence += 1
        else:
            period_ids = [rep_id.period_id]
            period_group_id = rep_id.period_group_id

        tz_date_start = self.env['time.tracking.actions'].get_tz_datetime(date_start, self.env.user)
        tz_date_end = self.env['time.tracking.actions'].get_tz_datetime(date_end, self.env.user)
        for period_id in period_ids:
            from_date = self.env['time.tracking.actions'].get_tz_datetime(period_id.from_date,
                                                                          self.env.user)
            to_date = self.env['time.tracking.actions'].get_tz_datetime(period_id.to_date, self.env.user)

            if origin in ('periodic', 'operational'):
                progress = 100
                tracking_date_start = date_start
                tracking_date_end = date_end
                tracking_duration = rep_id.duration
                tz_tracking_date_start = self.env['time.tracking.actions'].get_tz_datetime(
                    tracking_date_start, self.env.user)
                tz_tracking_date_end = self.env['time.tracking.actions'].get_tz_datetime(tracking_date_end,
                                                                                         self.env.user)
            else:
                initial_date = tz_date_start if tz_date_start > from_date else from_date
                ending_date = tz_date_end if tz_date_end < to_date else to_date

                tracking_date_start = self.env['lbm.period'].get_datetime_calendar(calendar_id,
                                                                                   self.env[
                                                                                       'time.tracking.actions'].remove_tz_datetime(
                                                                                       initial_date,
                                                                                       self.env.user),
                                                                                   'next')
                tracking_date_end = self.env['lbm.period'].get_datetime_calendar(calendar_id,
                                                                                 self.env[
                                                                                     'time.tracking.actions'].remove_tz_datetime(
                                                                                     ending_date,
                                                                                     self.env.user))

                tz_tracking_date_start = self.env['time.tracking.actions'].get_tz_datetime(
                    tracking_date_start, self.env.user)
                tz_tracking_date_end = self.env['time.tracking.actions'].get_tz_datetime(tracking_date_end,
                                                                                         self.env.user)

                tracking_duration = self.env['lbm.scenario'].get_duration_by_calendar(calendar_id,
                                                                  tz_tracking_date_start,
                                                                  tz_tracking_date_end)
                progress = tracking_duration * replanning_progress / rep_id.duration

            if step_id:
                qty = progress * step_id.product_qty / 100
            else:
                qty = progress * workorder_id.qty_production / 100

            if tracking_duration:
                tracking_cmd = {'baseline_id': rep_id.baseline_id.id,
                                'production_id': production_id.id,
                                'workorder_id': workorder_id.id,
                                'planned_workcenter_id': workcenter_id.id,
                                'step_id': step_id.id if step_id else None,
                                'analytic_id': analytic_id,
                                'tracking_origin': 'workorder' if not step_id else 'step',
                                'period_group_id': period_group_id.id,
                                'lbm_period_id': self.period_id.id,
                                'planned_period_id': period_id.id,
                                'calendar_id': calendar_id.id,
                                'expected_qty': qty,
                                'estimation_type': estimation_type,
                                'available': True,
                                'date_start': tracking_date_start,
                                'date_end': tracking_date_end,
                                'month_number': 0,
                                'day_number': 0,
                                # 'set_operators': rep_id.set_operators,
                                'timetracking_type': rep_id.timetracking_type,
                                'key': '{}.{}.{}.{}.{}.{}.{}.{}'.format(rep_id.baseline_id.id,
                                                                        rep_id.production_id.id,
                                                                        workorder_id.id, step_id.id if step_id else 0,
                                                                        rep_id.ite_period_id.id, analytic_id, 0, 0)}

                # Divide by Day
                if self.daily_tracking:
                    current_day = tz_tracking_date_start
                    wanted_days = list(set(calendar_id.attendance_ids.mapped('dayofweek')))
                    while current_day.strftime('%Y-%m-%d') <= tz_tracking_date_end.strftime('%Y-%m-%d'):
                        wanted_condition = str(current_day.weekday())
                        if wanted_condition in wanted_days:
                            schedule_date_start, schedule_date_end = self.env['lbm.scenario'].get_schedule_by_day(calendar_id,
                                                                                               current_day)
                            if schedule_date_end:
                                final_date_start = tracking_date_start if tracking_date_start > schedule_date_start else schedule_date_start
                                final_date_end = tracking_date_end if tracking_date_end < schedule_date_end else schedule_date_end

                                tz_final_date_start = self.env['time.tracking.actions'].get_tz_datetime(
                                    final_date_start, self.env.user)
                                tz_final_date_end = self.env['time.tracking.actions'].get_tz_datetime(
                                    final_date_end, self.env.user)

                                partial_duration = self.env['lbm.scenario'].get_duration_by_calendar(calendar_id, tz_final_date_start,
                                                                                 tz_final_date_end)
                                partial_qty = partial_duration * qty / tracking_duration

                                tracking_cmd_copy = dict(tracking_cmd)
                                month_number = final_date_end.month
                                day_number = final_date_end.day
                                tracking_cmd_copy.update({
                                    'estimation_type': estimation_type,
                                    'expected_qty': partial_qty,
                                    'date_start': final_date_start,
                                    'date_end': final_date_end,
                                    'month_number': month_number,
                                    'day_number': day_number,
                                    'key': '{}.{}.{}.{}.{}.{}.{}.{}'.format(self.baseline_id.id,
                                                                            production_id.id,
                                                                            workorder_id.id,
                                                                            step_id.id if step_id else 0,
                                                                            period_id.id,
                                                                            analytic_id, month_number,
                                                                            day_number)
                                })
                                cmds.append(tracking_cmd_copy)

                        current_day = current_day + timedelta(days=1)

                else:
                    cmds.append(tracking_cmd)
        return cmds

    def process_replanning_btn(self, workorder_id=None):
        if not self.env.user.has_group('aci_estimation.group_estimation_resident'):
            raise ValidationError(_('You are not allowed to do this process'))
        self.tracking_validated = False
        TimeTracking = self.env['mrp.timetracking']
        if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
            if request.session.get('session_workcenter'):
                workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
            else:
                workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)],
                                                                  limit=1)
            workcenter_ids, dic_supervised_wc = self.env['mrp.tracking.access'].get_supervised(workcenter_id.id)

        stored_keys = TimeTracking.search([('baseline_id', '=', self.baseline_id.id),
                                           ('lbm_period_id', '=', self.period_id.id)]).mapped('key')
        keys = []
        valid_workorder_ids = []
        records = []
        search_args = [('baseline_id', '=', self.baseline_id.id),
                        ('can_be_planned', '=', True),
                        ('can_be_estimated', '=', True),
                        ('start_date', '>=', self.period_start),
                        ('start_date', '<=', self.period_end)]
        if workorder_id:
            search_args.append(('workorder_id', '=', workorder_id))
        replanning_ids = self.env['mrp.timetracking.workorder'].search(search_args)
        for rep_id in replanning_ids:
            if rep_id.duration <= 0:
                raise ValidationError(_('{} has a problem with its duration.'.format(
                    rep_id.workorder_id.product_wo.complete_name)))
            records = self.create_tracking(records, rep_id)
            if rep_id.timetracking_type == 'mixed':
                for step_id in rep_id.workorder_id.step_ids:
                    records = self.create_tracking(records, rep_id, step_id)
        _records = []
        # Update or Create Keys, we need to do a one by one check because this validation was implemented later on -_-!
        for record in records:
            timetracking_id = TimeTracking.search([('key', '=', record['key'])])
            if timetracking_id:
                if self.period_start <= record['date_start'] <= self.period_end:
                    if self.env.user.has_group('aci_estimation.group_estimation_chief'):
                        if not workorder_id:
                            timetracking_id.write(record)
                        elif workorder_id == record['workorder_id']:
                            timetracking_id.write(record)

                    elif record['planned_workcenter_id'] in workcenter_ids:
                        if not workorder_id:
                            timetracking_id.write(record)
                        elif workorder_id == record['workorder_id']:
                            timetracking_id.write(record)
            else:
                if self.period_start <= record['date_start'] <= self.period_end:
                    if self.env.user.has_group('aci_estimation.group_estimation_chief'):
                        if not workorder_id:
                            _records.append(record)
                        elif workorder_id == record['workorder_id']:
                            _records.append(record)
                    elif record['planned_workcenter_id'] in workcenter_ids:
                        if not workorder_id:
                            _records.append(record)
                        elif workorder_id == record['workorder_id']:
                            _records.append(record)
            if record['expected_qty'] > 0:
                keys.append(record['key'])
            valid_workorder_ids.append(record['workorder_id'])

        TimeTracking.create(_records)
        # Unlink, again... checked one by one
        deleted_keys = list(set(stored_keys) - set(keys))
        timetracking_ids = TimeTracking.search([('key', 'in', deleted_keys)])
        if workorder_id:
            timetracking_ids = timetracking_ids.filtered(lambda r: r.workorder_id.id == workorder_id)
        for timetracking_id in timetracking_ids:
            if len(timetracking_id.tracking_ids) == 0:
                timetracking_id.unlink()
            else:
                timetracking_id.available = False

        self.process_estimation_btn(workorder_id)
        self.tracking_validated = True

    def move_multi_ite_btn(self):
        ite_ids = self.env['mrp.timetracking.workorder'].search([('baseline_id', '=', self.scenario_id.baseline_id.id),
                                                                 ('start_date', '>=', self.period_start),
                                                                 ('start_date', '<=', self.period_end)])
        period_ids = self.scenario_id.period_ids
        period_id = period_ids.filtered(lambda r: r.period_id.global_sequence == self.period_id.global_sequence + 1)

        if period_id:
            period_id = period_id.mapped('period_id')
            remove_ite_ids = []
            for ite_id in ite_ids.filtered(lambda r: r.replanning_progress > 0):
                dest_ite_ids = self.env['mrp.timetracking.workorder'].search([
                    ('workorder_id', '=', ite_id.workorder_id.id),
                    ('ite_period_id', '=', period_id.id)], order='start_date ASC')

                period_days = (period_id.to_date - period_id.from_date).days + 1
                if ite_id.ite_period_id.global_sequence < period_id.global_sequence:
                    period_lap = period_id.global_sequence - ite_id.ite_period_id.global_sequence
                    start_date = ite_id.start_date + timedelta(days=period_days * period_lap)
                    end_date = ite_id.end_date + timedelta(days=period_days * period_lap)
                else:
                    period_lap = ite_id.ite_period_id.global_sequence - period_id.global_sequence
                    start_date = ite_id.start_date - timedelta(days=period_days * period_lap)
                    end_date = ite_id.end_date - timedelta(days=period_days * period_lap)

                if dest_ite_ids:
                    if dest_ite_ids.filtered(lambda r: r.ite_progress > 0):
                        dest_ite_ids.write({'ite_progress': ite_id.replanning_progress + dest_ite_ids.ite_progress,
                                            'ite_qty_progress': ite_id.replanning_qty_progress + dest_ite_ids.ite_qty_progress})
                else:
                    ite_id.workorder_id.write({'tworkorder_ids':
                                                   [(0, False,
                                                     {'workorder_id': ite_id.workorder_id.id,
                                                      'period_id': ite_id.period_id.id,
                                                      'ite_period_id': period_id.id,
                                                      'period': period_id.name,
                                                      'start_date': start_date,
                                                      'end_date': end_date,
                                                      'planned_progress': 0,
                                                      'planned_qty_progress': 0,
                                                      'ite_progress': ite_id.replanning_progress,
                                                      'ite_qty_progress': ite_id.replanning_qty_progress,
                                                      'lbm_workorder_id': ite_id.lbm_workorder_id.id,
                                                      'workcenter_id': ite_id.workorder_id.resource_id.id,
                                                      'timetracking_type': ite_id.workorder_id.timetracking_type
                                                      if ite_id.workorder_id.timetracking_type else 'workorder',
                                                      'duration': ite_id.duration}
                                                     )]})
                ite_id.ite_progress = ite_id.executed_progress if ite_id.executed_progress > 0 else 0
                ite_id.ite_qty_progress = ite_id.executed_qty_progress if ite_id.executed_qty_progress > 0 else 0
                if ite_id.planned_progress == 0 and ite_id.executed_progress == 0:
                    remove_ite_ids.append(ite_id.id)
            self.env['mrp.timetracking.workorder'].browse(remove_ite_ids).unlink()

    def move_ite_btn(self):
        Estimation = self.env['mrp.estimation']
        LbmPeriod = self.env['lbm.period']
        context = self.env.context
        Timetracking = self.env['mrp.timetracking']
        ITE = self.env['mrp.timetracking.workorder']
        model = context.get('model', None)
        if model == 'mrp.timetracking':
            _ids = []
            for timetracking_id in Timetracking.browse(context.get('active_ids')):
                ite_id = ITE.search([('baseline_id', '=', timetracking_id.baseline_id.id),
                                     ('end_date', '>=', timetracking_id.date_start),
                                     ('start_date', '<=', timetracking_id.date_start),
                                     ('workorder_id', '=', timetracking_id.workorder_id.id)])
                if ite_id:
                    _ids.append(ite_id.id)
            ite_ids = ITE.browse(_ids).filtered(lambda r: r.replanning_progress > 0)
        else:
            ite_ids = self.env['mrp.timetracking.workorder'].browse(context.get('active_ids', []))

        if context.get('ite_ids', []):
            ite_ids = self.env['mrp.timetracking.workorder'].browse(context.get('ite_ids', []))

        for ite_id in ite_ids:
            # Validate current estimation
            estimation_id = Estimation.search([('workcenter_id', '=', ite_id.workcenter_id.id),
                                               ('start_period', '<=', ite_id.start_date),
                                               ('end_period', '>=', ite_id.end_date),
                                               ('estimation_type', '=', 'period'),
                                               ('warehouse_id', '=', ite_id.workorder_id.warehouse_id.id)], limit=1)
            if estimation_id and estimation_id.period_status not in ('draft', 'open'):
                raise ValidationError(_('The source estimation is not open anymore.'))

            dest_ite_ids = self.env['mrp.timetracking.workorder'].search([
                ('workorder_id', '=', ite_id.workorder_id.id),
                ('ite_period_id', '=', self.period_id.id)], order='start_date ASC')

            period_days = (self.period_end - self.period_start).days + 1
            if ite_id.ite_period_id.global_sequence < self.period_id.global_sequence:
                period_lap = self.period_id.global_sequence - ite_id.ite_period_id.global_sequence
                start_date = ite_id.start_date + timedelta(days=period_days * period_lap)
                end_date = ite_id.end_date + timedelta(days=period_days * period_lap)
            else:
                period_lap = ite_id.ite_period_id.global_sequence - self.period_id.global_sequence
                start_date = ite_id.start_date - timedelta(days=period_days * period_lap)
                end_date = ite_id.end_date - timedelta(days=period_days * period_lap)

            # Validate destiny estimation
            dest_estimation_id = Estimation.search([('workcenter_id', '=', ite_id.workcenter_id.id),
                                               ('start_period', '<=', start_date),
                                               ('end_period', '>=', end_date),
                                               ('warehouse_id', '=', ite_id.workorder_id.warehouse_id.id)], limit=1)
            if dest_estimation_id and dest_estimation_id.period_status not in ('draft', 'open'):
                raise ValidationError(_('The destiny estimation is not open anymore.'))

            if dest_ite_ids:
                limit = ite_id.workorder_id.qty_production
                ite_progress = ite_id.replanning_progress + dest_ite_ids.ite_progress
                ite_qty_progress = ite_id.replanning_qty_progress + dest_ite_ids.ite_qty_progress
                if dest_ite_ids.filtered(lambda r: r.ite_progress > 0):
                    dest_ite_ids.write({'ite_progress': ite_progress if ite_progress <= 100 else 100,
                                        'ite_qty_progress': ite_qty_progress if ite_qty_progress <= limit else limit})
            else:
                ite_id.workorder_id.write({'tworkorder_ids':
                                            [(0, False,
                                              {'workorder_id': ite_id.workorder_id.id,
                                               'period_id': ite_id.period_id.id,
                                               'ite_period_id': self.period_id.id,
                                               'period': self.period_id.name,
                                               'start_date': start_date,
                                               'end_date': end_date,
                                               'planned_progress': 0,
                                               'planned_qty_progress': 0,
                                               'ite_progress': ite_id.replanning_progress,
                                               'ite_qty_progress': ite_id.replanning_qty_progress,
                                               'lbm_workorder_id': ite_id.lbm_workorder_id.id,
                                               'workcenter_id': ite_id.workcenter_id.id,
                                               'timetracking_type': ite_id.workorder_id.timetracking_type
                                               if ite_id.workorder_id.timetracking_type else 'workorder',
                                               'duration': ite_id.duration,
                                               'can_be_estimated': ite_id.can_be_estimated}
                                              )]})
            ite_id.ite_progress = ite_id.executed_progress if ite_id.executed_progress > 0 else 0
            ite_id.ite_qty_progress = ite_id.executed_qty_progress if ite_id.executed_qty_progress > 0 else 0
            ite_id.period = self.period_id.name
            if ite_id.planned_progress == 0 and ite_id.executed_progress == 0:
                self.env['mrp.timetracking.workorder'].browse([ite_id.id]).unlink()
            self.process_replanning_btn(workorder_id=ite_id.workorder_id.id)
            lbm_period_id = LbmPeriod.search([('baseline_id', '=', ite_id.baseline_id.id),
                                              ('period_start', '<=', ite_id.start_date),
                                              ('period_end', '>=', ite_id.start_date)])
            lbm_period_id.process_replanning_btn(workorder_id=ite_id.workorder_id.id)

    def process_estimation_btn(self, workorder_id=None):
        EstimationWizard = self.env['mrp.estimation.wizard']
        Estimation = self.env['mrp.estimation']
        TimeTracking = self.env['mrp.timetracking']

        # Estimation Workcenters
        for production_id in self.scenario_id.baseline_id.production_ids:
            workcenter_ids = production_id.workorder_ids.mapped('resource_id').ids
            TimeTracking.create_estimation_workcenter(workcenter_ids)

        # TimeTracking.delete_estimation_workcenter()  # Not used on any scenario
        self.env['mrp.production'].compute_workcenter_btn()

        # Estimation
        search_args = [('baseline_id', '=', self.baseline_id.id),
                         ('can_be_planned', '=', True),
                         ('start_date', '>=', self.period_start),
                         ('start_date', '<=', self.period_end)]
        if workorder_id:
            search_args.append(('workorder_id', '=', workorder_id))
        ite_ids = self.env['mrp.timetracking.workorder'].search(search_args)
        for ite_id in ite_ids:
            if self.baseline_type == 'periodic':
                period_group_id = self.period_id.group_id
            else:
                period_group_id = ite_id.workcenter_id.period_group_id

            day_start = self.period_id.from_date
            day_end = self.period_id.to_date
            days = (day_end - day_start).days + 1
            period_ids = []
            for current_day in range(0, days, 1):
                looking_day = day_start + timedelta(days=current_day)
                period_id = period_group_id.period_ids. \
                    filtered(lambda _r: _r.from_date < looking_day <= _r.to_date)
                if period_id and period_id not in period_ids:
                    period_ids.append(period_id)

            for period_id in period_ids:
                estimation_ids = Estimation.search([('workcenter_id', '=', ite_id.workcenter_id.id),
                                                    ('period_id', '=', period_id.id),
                                                    ('warehouse_id', '=', ite_id.workorder_id.warehouse_id.id)])
                if not estimation_ids:
                    EstimationWizard.build_estimation(period_id.from_date, period_id.to_date,
                                                      ite_id.workcenter_id, ite_id.workcenter_id.employee_id,
                                                      period_id)
                else:
                    estimation_ids.update_estimation_btn()

    def build_search_args(self):
        search_args = [('lbm_period_id', '=', self.period_id.id),
                       ('baseline_id', '=', self.scenario_id.baseline_id.id)]
        if not self.env.user.has_group('aci_estimation.group_estimation_chief'):
            if request.session.get('session_workcenter'):
                workcenter_id = self.env['mrp.workcenter'].browse([request.session.get('session_workcenter')])
            else:
                workcenter_id = self.env['mrp.workcenter'].search([('employee_id.user_id', '=', self.env.user.id)],
                                                                  limit=1)
            workcenter_ids, dic_supervised_wc = self.env['mrp.tracking.access'].get_supervised(workcenter_id.id)
            search_args.append(('workcenter_id', 'in', workcenter_ids))
        return search_args

    def show_scenario_step_btn(self):
        step_ids = self.env['mrp.timetracking'].search(self.build_search_args())\
            .mapped('workorder_id').mapped('step_ids')
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'lbm_work_order_step_tree_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Steps',
            'views': [(view_id.id, 'tree')],
            'res_model': 'lbm.work.order.step',
            'domain': [('id', 'in', step_ids.ids)],
            'target': 'current',
            'context': {'search_default_Work_order': 1},
        }

    def show_tracking_btn(self):
        tracking_ids = self.env['mrp.timetracking'].search(self.build_search_args())
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_tree_view')
        calendar_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_timetracking_calendar_view')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Activity',
            'views': [(view_id.id, 'tree'), (calendar_view_id.id, 'calendar')],
            'res_model': 'mrp.timetracking',
            'domain': [('id', 'in', tracking_ids.ids)],
            'target': 'current'
        }

    def show_estimation_btn(self):
        workcenter_ids = self.env['mrp.timetracking'].search(self.build_search_args()).\
            mapped('workcenter_id').ids

        input_wc_ids = self.env['mrp.workcenter.productivity'].search([('final_start_date', '>=', self.period_start),
                         ('final_start_date', '<=', self.period_end)]).mapped('resource_id').ids

        workcenter_ids = self.env['mrp.workcenter'].browse(list(set(workcenter_ids + input_wc_ids)))

        if self.baseline_type == 'periodic':
            _domain = [('period_id', '=', self.period_id.id),
                       ('workcenter_id', 'in', workcenter_ids.ids)]
        else:
            tracking_ids = []
            for workcenter_id in workcenter_ids:
                day_start = self.period_id.from_date
                day_end = self.period_id.to_date
                days = (day_end - day_start).days + 1
                period_ids = []
                for current_day in range(0, days, 1):
                    looking_day = day_start + timedelta(days=current_day)
                    period_id = workcenter_id.period_group_id.period_ids. \
                        filtered(lambda _r: _r.from_date < looking_day <= _r.to_date)
                    if period_id:
                        period_ids.append(period_id.id)
                period_ids = list(set(period_ids))
                warehouse_ids = self.scenario_id.baseline_id.production_ids.mapped('context_warehouse').ids
                tmp_tracking_ids = self.env['mrp.estimation'].search([('workcenter_id', '=', workcenter_id.id),
                                                                      ('period_id', 'in', period_ids),
                                                                      ('warehouse_id', 'in', warehouse_ids)]).ids
                tmp_tracking_ids = list(set(tmp_tracking_ids))

                for _id in tmp_tracking_ids:
                    tracking_ids.append(_id)

            _domain = [('id', 'in', tracking_ids)]
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_estimation_tree_view')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Estimation',
            'views': [(view_id.id, 'tree'), (False, 'form')],
            'res_model': 'mrp.estimation',
            'domain': _domain,
            'target': 'current',
            'context': {'search_default_filter_periodic_estimation': 1}
        }
