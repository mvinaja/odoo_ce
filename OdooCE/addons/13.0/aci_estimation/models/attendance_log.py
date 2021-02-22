# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AttendanceLog(models.Model):
    _name = 'attendance.log'
    _description = 'attendance.log'
    _order = 'period_id desc, employee_id, attendance_log_date asc'

    employee_id = fields.Many2one('hr.employee', 'Employee')
    attendance_log_date = fields.Datetime('Att. Log Date')
    pin = fields.Char(compute='_compute_pin', inverse='inverse_value', store=True)

    structure_type_id = fields.Many2one(
        'hr.payroll.structure.type', compute='_compute_contract_data', store=True, string='Salary Structure Type')
    calendar_id = fields.Many2one(
        'resource.calendar', compute='_compute_contract_data', store=True, string='Schedule')
    department_id = fields.Many2one('hr.department', string="Department",
        related="employee_id.department_id", store=True, readonly=True)
    period_id_computed = fields.Many2one('payment.period', string='Period Com.',
        compute='_compute_period', index=True, ondelete='restrict', search='_search_period', compute_sudo=True)
    period_id = fields.Many2one('payment.period', compute='_compute_period', string='Period',
        store=True, inverse='inverse_value', ondelete='restrict', compute_sudo=True)

    date_computed = fields.Date('Date')
    day_computed = fields.Char('Day')
    hour_computed = fields.Float('Hour')

    created_by_user = fields.Boolean('Created By User')
    reviewed = fields.Boolean(default=False)
    discarded = fields.Boolean(default=False)

    # Dummy to search
    prev_period = fields.Boolean()
    # hour_search = fields.Float('Hour')

    @api.model
    def create(self, vals):
        context = self.env.context
        vals['created_by_user'] = not context.get('imported', False)
        return super(AttendanceLog, self).create(vals)

    def name_get(self):
        if self.employee_id and self.attendance_log_date:
            return [(self.id, '{0} > {1}'.format(self.employee_id.name, self.attendance_log_date))]
        else:
            return super(AttendanceLog, self).name_get()

    @api.model
    def _read_group_process_groupby(self, gb, query):
        response = super(AttendanceLog, self)._read_group_process_groupby(gb, query)
        if self.env.context.get('custom_datetime_format', False):
            split = gb.split(':')
            field_type = self._fields[split[0]].type
            gb_function = split[1] if len(split) == 2 else None
            temporal = field_type in ('date', 'datetime')
            if temporal:
                display_formats = {
                    # 'day': 'dd MMM yyyy', # yyyy = normal year
                    'day': 'dd.MMMM - EEE', # yyyy = normal year
                    'week': "'W'w YYYY",  # w YYYY = ISO week-year
                    'month': 'MMMM yyyy',
                    'quarter': 'QQQ yyyy',
                    'year': 'yyyy',
                }
            response['display_format'] = temporal and display_formats[gb_function or 'month'] or None

        return response

    # @api.model
    # def search(self, args, offset=0, limit=None, order=None, count=False):
    #     if args:
    #         self._verify_custom_search_arguments(args)
    #     return super(AttendanceLog, self).search(args, offset=offset, limit=limit, order=order, count=count)

    def _search_period(self, operator, value):
        assert operator == 'in'
        ids = []
        for period in self.env['payment.period'].browse(value):
            # self._cr.execute("""
            #         SELECT a.id
            #             FROM attendance_log a
            #         WHERE %(date_to)s >= a.attendance_log_date
            #             AND %(date_from)s <= a.attendance_log_date
            #         GROUP BY a.id""", {'date_from': period.from_date,
            #                            'date_to': period.to_date,})
            self._cr.execute("""
                    SELECT a.id
                        FROM attendance_log a
                    WHERE %(date_to)s >= a.date_computed
                        AND %(date_from)s <= a.date_computed
                    GROUP BY a.id""", {'date_from': period.from_date,
                                       'date_to': period.to_date,})
            ids.extend([row[0] for row in self._cr.fetchall()])
        return [('id', 'in', ids)]

    def inverse_value(self):
        return 'done'

    @api.depends('employee_id')
    def _compute_contract_data(self):
        Contract = self.env['hr.contract']
        for _id in self:
            if _id.employee_id:
                contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
                if contract_id:
                    _id.structure_type_id = contract_id.structure_type_id.id
                    resource_calendar_id = contract_id.resource_calendar_id
                    if resource_calendar_id:
                        _id.calendar_id = resource_calendar_id.id


    @api.depends('employee_id', 'attendance_log_date', 'date_computed')
    def _compute_period(self):
        """Links the attendance log to the corresponding period
        """
        Contract = self.env['hr.contract']
        for _id in self:
            if _id.attendance_log_date:
                contract_id = Contract.search([('employee_id', '=', _id.employee_id.id)], limit=1)
                if contract_id:
                    for grp in contract_id.period_group_id:
                        period_id = self.env['payment.period'].search([
                            ('to_date', '>=', _id.date_computed),
                            ('from_date', '<=', _id.date_computed),
                            ('group_id', '=', grp.period_group_id.id)], limit=1)
                        if period_id:
                            _id.period_id_computed = period_id
                            _id.period_id = period_id

    @api.depends('employee_id')
    def _compute_pin(self):
        for _id in self:
            _id.pin = _id.employee_id.pin

    # @api.model
    # def _verify_custom_search_arguments(self, args):
    #     PeriodGp = self.env['payment.period.group']
    #     prev_periods = PeriodGp.get_general_previous_period()
    #
    #     self._verify_custom_argument(args, 'prev_period', 'period_id', 'in', prev_periods)
    #
    # @api.model
    # def _verify_custom_argument(self, args, field, new_field=False, new_op=False, new_value=False):
    #     index = self._get_index_search_field(field, args)
    #     if index != -1:
    #         if new_field:
    #             args[index][0] = new_field
    #         if new_op:
    #             args[index][1] = new_op
    #         if new_value:
    #             args[index][2] = new_value

    @api.model
    def _get_index_search_field(self, field, args):
        try:
            index = list(map(lambda r: field in r, args)).index(True)
        except ValueError:
            index = -1
        return index

    @api.model
    def get_attendance_logs_by_period_mapped(self, period_id, _fields, employee_ids=False, search_date=False):
        domain = [('period_id', '=', period_id.id), ('discarded', '=', False)]
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))
        if search_date:
            domain.append(('date_computed', '=', search_date))
        return self.search(domain).mapped(lambda r: r and\
            {f: t == 'm2o' and r[f].id or r[f] for f, t in _fields.items()} or None)

    @api.model
    def save_massive_attendance_log(self, new_records):
        fnames = new_records[0].keys()
        values = ''
        for record in new_records:
            values += '('
            rec = ''
            for key in fnames:
                value = record[key]
                rec += (type(value).__name__ == 'str' and "'" + value + "'" or str(value)) + ','
            values += rec[:-1] + '),'
        values = values[:-1]

        sql = 'INSERT INTO attendance_log (' + ', '.join(fnames) + ') VALUES ' + values + ' RETURNING id'
        self.env.cr.execute(sql)
        ids = [r[0] for r in self.env.cr.fetchall()]
        self.env.cache.invalidate()

        _ids = self.browse(ids)
        _ids._recompute_todo(self._fields['structure_type_id'])
        _ids._recompute_todo(self._fields['calendar_id'])
        _ids._recompute_todo(self._fields['department_id'])
        _ids._recompute_todo(self._fields['period_id'])
        _ids._recompute_todo(self._fields['pin'])
        self.recompute()
