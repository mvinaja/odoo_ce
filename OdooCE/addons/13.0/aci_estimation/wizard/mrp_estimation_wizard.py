# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT

class MrpTimetrackingEstimationWizard(models.TransientModel):
    _name = 'mrp.estimation.wizard'
    _description = 'mrp.estimation.wizard'
    _rec_name = 'workcenter_id'

    @api.model
    def _get_default_period_group(self):
        workcenter_id = self.env['mrp.workcenter'].browse([self.env.context.get('default_workcenter_id')])

        timetracking_ids = self.env['mrp.timetracking'].search([('workcenter_id', '=', workcenter_id.id),
                                                                ('production_id.state', 'not in', ['done', 'cancel'])])
        period_group_ids = timetracking_ids.mapped('period_group_id').ids
        return period_group_ids[0] if period_group_ids else None

    @api.model
    def _get_default_period(self):
        workcenter_id = self.env['mrp.workcenter'].browse([self.env.context.get('default_workcenter_id')])

        timetracking_ids = self.env['mrp.timetracking'].search([('workcenter_id', '=', workcenter_id.id),
                                                                ('production_id.state', 'not in', ['done', 'cancel'])])
        period_group_ids = timetracking_ids.mapped('period_group_id')
        period_group_id = period_group_ids[0] if period_group_ids else None
        current_period_id = None
        if period_group_id:
            for period_id in period_group_id.period_ids:
                if period_id.from_date < datetime.now() <= period_id.to_date:
                    current_period_id = period_id.id
        return current_period_id

    readonly = fields.Boolean(default=False)
    workcenter_id = fields.Many2one('mrp.workcenter')
    employee_id = fields.Many2one(related='workcenter_id.employee_id')
    domain_period_ids = fields.Many2many('payment.period')
    domain_period_group_ids = fields.Many2many('payment.period.group', string='Period Group', required=True, ondelete='cascade')
    period_id = fields.Many2one('payment.period', required=True, default=_get_default_period, ondelete='restrict')
    period_from = fields.Datetime(related='period_id.from_date', readonly=True)
    period_to = fields.Datetime(related='period_id.to_date', readonly=True)
    period_group_id = fields.Many2one('payment.period.group', string='Period Group', required=True, default=_get_default_period_group, ondelete='cascade')

    @api.model
    def default_get(self, fields):
        res = super(MrpTimetrackingEstimationWizard, self).default_get(fields)
        timetracking_ids = self.env['mrp.timetracking'].search([('workcenter_id', '=', res['workcenter_id']),
                                                                ('production_id.state', 'not in', ['done', 'cancel'])])
        period_ids = timetracking_ids.mapped('period_id').ids
        for period_group in timetracking_ids.mapped('period_group_id'):
            for period_id in period_group.period_ids:
                if period_id.from_date < datetime.now() <= period_id.to_date and period_id.id not in period_ids:
                    period_ids.append(period_id.id)
        res['domain_period_group_ids'] = [(6, 0, timetracking_ids.mapped('period_group_id').ids)]
        res['domain_period_ids'] = [(6, 0, period_ids)]
        return res

    def create_estimation_btn(self):
        if not self.period_id or not self.workcenter_id:
            raise ValidationError('You need a Period and a Workcenter to Estimate')
        self.build_estimation(self.period_from, self.period_to, self.workcenter_id, self.employee_id,
                              self.period_id)

    def update_parent_estimation(self, period_id, warehouse_id):
        daily_estimation_ids = self.env['mrp.estimation'].search([('period_id', '=', period_id.id),
                                                                  ('warehouse_id', '=', warehouse_id.id)])
        for d_estimation_id in daily_estimation_ids.filtered(lambda r: r.estimation_type == 'daily'):
            d_estimation_id.write({'parent_id': daily_estimation_ids.filtered(lambda r: r.estimation_type == 'period'
                                                                              and r.workcenter_id == d_estimation_id.workcenter_id
                                                                              and r.employee_id == d_estimation_id.employee_id
                                                                              and r.warehouse_id == warehouse_id).id})

    def build_estimation(self, wanted_day, limit_day, workcenter_id, employee_id, period_id):
        Estimation = self.env['mrp.estimation']
        Estimation.search([('workcenter_id', '=', None),
                           ('period_id', '=', period_id.id)]).unlink()

        warehouse_ids = self.env['mrp.timetracking'].search([('workcenter_id', '=', workcenter_id.id),
                                                             ('period_id', '=', period_id.id)]).mapped('warehouse_id')
        for warehouse_id in warehouse_ids:
            estimation_dic = []
            current_day = wanted_day
            while current_day.strftime('%Y-%m-%d') < limit_day.strftime('%Y-%m-%d'):
                if workcenter_id.resource_calendar_id.attendance_ids.filtered(lambda r: int(r.dayofweek) == int(current_day.weekday())):
                    estimation_id = Estimation.search([('workcenter_id', '=', workcenter_id.id),
                                                       ('period_id', '=', period_id.id),
                                                       ('day', '=', current_day),
                                                       ('estimation_type', '=', 'daily'),
                                                       ('warehouse_id', '=', warehouse_id.id)])
                    # Use period data
                    block_ids = self.get_activity_block(None, 'period', employee_id, period_id, warehouse_id)
                    productivity_ids = self.get_productivity(None, 'period', workcenter_id, period_id, warehouse_id)
                    ttracking_ids = self.get_timetracking(None, 'period', workcenter_id, period_id, warehouse_id)
                    if estimation_id:
                        if workcenter_id.estimation_type == 'daily':
                            estimation_id.write({'block_ids': [(6, 0, block_ids.ids)],
                                                 'productivity_ids': [(6, 0, productivity_ids.ids)],
                                                 'timetracking_ids': [(6, 0, ttracking_ids.ids)]})
                        else:
                            estimation_id.unlink()
                    elif workcenter_id.estimation_type == 'daily':
                        estimation_dic.append({'workcenter_id': workcenter_id.id,
                                               'period_group_id': period_id.group_id.id,
                                               'period_id': period_id.id,
                                               'warehouse_id': warehouse_id.id,
                                               'day': current_day,
                                               'estimation_type': 'daily',
                                               'block_ids': [(6, 0, block_ids.ids)],
                                               'productivity_ids': [(6, 0, productivity_ids.ids)],
                                               'timetracking_ids': [(6, 0, ttracking_ids.ids)]})
                current_day = current_day + timedelta(days=1)
            # CREATE PERIOD ESTIMATION
            estimation_id = Estimation.search([('workcenter_id', '=', workcenter_id.id),
                                               ('period_id', '=', period_id.id),
                                               ('warehouse_id', '=', warehouse_id.id),
                                               ('estimation_type', '=', 'period')])
            block_ids = self.get_activity_block(None, 'period', employee_id, period_id, warehouse_id)
            productivity_ids = self.get_productivity(None, 'period', workcenter_id, period_id, warehouse_id)
            ttracking_ids = self.get_timetracking(None, 'period', workcenter_id, period_id, warehouse_id)
            status = 'open' if block_ids else 'draft'
            if estimation_id:
                estimation_id.write({'block_ids': [(6, 0, block_ids.ids)],
                                     'productivity_ids': [(6, 0, productivity_ids.ids)],
                                     'timetracking_ids': [(6, 0, ttracking_ids.ids)],
                                     'period_status': status})
            else:
                estimation_dic.append({'workcenter_id': workcenter_id.id,
                                       'period_group_id': period_id.group_id.id,
                                       'period_id': period_id.id,
                                       'estimation_type': 'period',
                                       'warehouse_id': warehouse_id.id,
                                       'block_ids': [(6, 0, block_ids.ids)],
                                       'productivity_ids': [(6, 0, productivity_ids.ids)],
                                       'timetracking_ids': [(6, 0, ttracking_ids.ids)],
                                       'period_status': status})
            Estimation.create(estimation_dic)
            self.update_parent_estimation(period_id=period_id, warehouse_id=warehouse_id)

    def get_activity_block(self, day, type, employee_id, period_id, warehouse_id):
        blocks = [('block_type', '=', 'active'),
                  ('employee_id', '=', employee_id.id),
                  ('final_end_date', '>=', period_id.from_date),
                  ('final_end_date', '<=', period_id.to_date),
                  ('warehouse_id', '=', warehouse_id.id)]
        if type == 'daily':
            start = self.env['time.tracking.actions'].remove_tz_datetime(
                datetime.strptime('{} 00:00:00'.format(day.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                self.env.user)
            end = self.env['time.tracking.actions'].remove_tz_datetime(
                datetime.strptime('{} 23:59:59'.format(day.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                self.env.user)
            blocks.append(('final_start_date', '>=', start))
            blocks.append(('final_start_date', '<=', end))
        return self.env['hr.productivity.block'].search(blocks)

    def get_productivity(self, day, type, workcenter_id, period_id, warehouse_id):
        search_args = [('resource_id', '=', workcenter_id.id), ('warehouse_id', '=', warehouse_id.id)]
        if type == 'daily':
            start = self.env['time.tracking.actions'].remove_tz_datetime(
                datetime.strptime('{} 00:00:00'.format(day.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                self.env.user)
            end = self.env['time.tracking.actions'].remove_tz_datetime(
                datetime.strptime('{} 23:59:59'.format(day.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                self.env.user)
            search_args.append(('final_start_date', '>=', start))
            search_args.append(('final_start_date', '<=', end))
        else:
            search_args.append(('final_start_date', '>=', period_id.from_date))
            search_args.append(('final_start_date', '<=', period_id.to_date))
        return self.env['mrp.workcenter.productivity'].search(search_args)

    def get_timetracking(self, day, type, workcenter_id, period_id, warehouse_id):
        search_args = [('workcenter_id', '=', workcenter_id.id),
                       ('date_end', '>=', period_id.from_date),
                       ('date_end', '<=', period_id.to_date),
                       ('warehouse_id', '=', warehouse_id.id)]
        if type == 'daily':
            start = self.env['time.tracking.actions'].remove_tz_datetime(
                datetime.strptime('{} 00:00:00'.format(day.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                self.env.user)
            end = self.env['time.tracking.actions'].remove_tz_datetime(
                datetime.strptime('{} 23:59:59'.format(day.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                self.env.user)
            search_args.append(('date_start', '>=', start))
            search_args.append(('date_start', '<=', end))
        return self.env['mrp.timetracking'].search(search_args)


class MrpTimetrackingEstimationCrewWizard(models.TransientModel):
    _name = 'mrp.estimation.crew.wizard'
    _description = 'mrp.estimation.crew.wizard'

    employee_crew_ids = fields.One2many('mrp.estimation.crew.employee.wizard', 'crew_id', string='Crew')
    employee_ids = fields.One2many('mrp.estimation.crew.employee.wizard', 'main_id', string='Responsible')
    date_ids = fields.One2many('mrp.estimation.crew.dates.wizard', 'crew_id')
    warehouse_id = fields.Many2one('stock.warehouse')

    @api.model
    def default_get(self, fields):
        res = super(MrpTimetrackingEstimationCrewWizard, self).default_get(fields)
        Block = self.env['hr.productivity.block']
        context = self._context
        estimation_ids = self.env['mrp.estimation'].browse(context.get('active_ids'))

        days = estimation_ids.mapped('day')
        date_ids = [(0, False, {'block_date': day,
                                'name': day.strftime('%a %m/%d')}) for day in days]

        employee_crew_ids = []
        for employee_id in estimation_ids.mapped('workcenter_id').mapped('employee_ids'):
            has_activity_block = []
            for day in days:
                start = datetime.combine(day, datetime.min.time()).replace(hour=0, minute=0,
                                                                           second=0,
                                                                           microsecond=0)
                end = datetime.combine(day, datetime.min.time()).replace(hour=23, minute=59,
                                                                         second=59,
                                                                         microsecond=0)

                has_activity_block.append(True if Block.search([('employee_id', '=', employee_id.id),
                                                                ('final_start_date', '>=', start),
                                                                ('final_start_date', '<=', end)]) else False)
            if False in has_activity_block:
                employee_crew_ids.append((0, False, {'employee_id': employee_id.id}))

        employee_ids = []
        Crew = self.env['mrp.estimation.crew.employee.wizard']
        for employee_id in estimation_ids.filtered(lambda r: r.can_create_block is True).mapped('employee_id'):
            crew_id = Crew.create({'employee_id': employee_id.id,
                                   'block_available': True})
            employee_ids.append(crew_id.id)

        res['employee_crew_ids'] = employee_crew_ids
        res['employee_ids'] = [(6, 0, employee_ids)]
        res['date_ids'] = date_ids
        return res

    def create_activity_btn(self):
        context = self._context
        estimation_ids = self.env['mrp.estimation'].browse(context.get('active_ids'))
        for estimation_id in estimation_ids:
            for date_id in self.date_ids:
                tz_wanted_date = datetime.combine(date_id.block_date, datetime.min.time())
                wanted_date = self.env['time.tracking.actions'].remove_tz_datetime(tz_wanted_date, self.env.user)
                for employee_id in self.employee_crew_ids:
                    end = self.env['time.tracking.actions'].remove_tz_datetime(
                        datetime.strptime('{} 23:59:59'.format(wanted_date.date()), DEFAULT_SERVER_DATETIME_FORMAT),
                        self.env.user)
                    if not self.env['hr.productivity.block'].search([('final_start_date', '>=', end),
                                                                 ('employee_id', '=', employee_id.employee_id.id)]):
                        self.env['hr.productivity.block'].generate_blocks(wanted_date, None, validate_time=False,
                                                                          _employee_id=employee_id.employee_id,
                                                                          warehouse_id=estimation_id.warehouse_id.id)
                for employee_id in self.employee_ids:
                    self.env['hr.productivity.block'].generate_blocks(wanted_date, None, validate_time=False,
                                                                      _employee_id=employee_id.employee_id,
                                                                      block_available=employee_id.block_available,
                                                                      warehouse_id=estimation_id.warehouse_id.id)
            estimation_id.update_activity_block_btn()


class MrpTimetrackingEstimationCrewEmployeeWizard(models.TransientModel):
    _name = 'mrp.estimation.crew.employee.wizard'
    _description = 'mrp.estimation.crew.employee.wizard'

    crew_id = fields.Many2one('mrp.estimation.crew.wizard')
    main_id = fields.Many2one('mrp.estimation.crew.wizard')
    employee_id = fields.Many2one('hr.employee')
    block_available = fields.Boolean(string='Available', default=True)


class MrpTimetrackingEstimationDatesWizard(models.TransientModel):
    _name = 'mrp.estimation.crew.dates.wizard'
    _description = 'mrp.estimation.crew.dates.wizard'

    crew_id = fields.Many2one('mrp.estimation.crew.wizard')
    employee_id = fields.Many2one('mrp.estimation.crew.employee.wizard')
    block_date = fields.Date('Date')
    name = fields.Char('Day')

