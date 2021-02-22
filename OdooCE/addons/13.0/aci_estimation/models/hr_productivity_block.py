# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT
from odoo.exceptions import ValidationError

import datetime, pytz
from datetime import timedelta


class HrproductivityBlock(models.Model):
    _name = 'hr.productivity.block'
    _description = 'hr.productivity.block'
    _order = 'employee_id ASC,final_start_date DESC'

    name = fields.Char(compute='_compute_name')
    employee_id = fields.Many2one('hr.employee')
    dayofweek = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday')
    ], 'Day of Week', compute="_compute_dayofweek", store=True)
    start_date = fields.Datetime('Start Activity')
    end_date = fields.Datetime('End Activity')
    offset_start_duration = fields.Float('Offset start minutes')
    offset_end_duration = fields.Float('Offset end minutes')
    offset_start_date = fields.Datetime('Offset Start', compute='_compute_offset_date')
    offset_end_date = fields.Datetime('Offset End', compute='_compute_offset_date')
    final_start_date = fields.Datetime('Final Start Activity', compute='_compute_final_date', store=True)
    final_end_date = fields.Datetime('Final End Activity', compute='_compute_final_date', store=True)
    duration = fields.Float('Duration', compute='_compute_duration', store=True)
    fixed_duration = fields.Float('Fixed Duration', default=0.0)
    status = fields.Selection([('draft', 'Draft'), ('closed', 'Locked')], default='draft')
    block_type = fields.Selection([('active', 'Active'), ('inactive', 'Inactive')], default='active')
    block_origin = fields.Selection([('delay', 'Delay'),
                                     ('calendar', 'Calendar'),
                                     ('incidence', 'Incidence'),
                                     ('payable', 'Payable Incidence'),
                                     ('timeoff', 'Calendar TimeOff'),
                                     ('extra', 'After Hours')
                                     ], default='calendar')
    block_available = fields.Boolean(default=True)
    resource_calendar_attendance_id = fields.Many2one('resource.calendar.attendance')
    tolerance = fields.Float(0) #ToDo
    parent_id = fields.Many2one('hr.productivity.block', ondelete='set null')
    period_id = fields.Many2one('payment.period', compute='_compute_period', string='Period',
                                store=True, inverse='inverse_value', ondelete='restrict')
    contract_id = fields.Many2one('hr.contract', compute='_compute_contract', store=True)
    incidence_id = fields.Many2one('attendance.incidence')
    sequence = fields.Integer(compute='_compute_sequence')
    warehouse_id = fields.Many2one('stock.warehouse')

    @api.model
    def create(self, vals):
        res = super(HrproductivityBlock, self).create(vals)
        estimation_ids = self.env['mrp.estimation'].search([('employee_id', 'in', res.mapped('employee_id').ids),
                                                            ('estimation_type', '=', 'period'),
                                                            ('start_period', '<=', res.final_start_date),
                                                            ('end_period', '>=', res.final_start_date)])
        if estimation_ids:
            to_update = []
            for estimation_id in estimation_ids:
                if not estimation_id.period_status or estimation_id.period_status in ('draft', 'open'):
                    to_update.append(estimation_id)

            if to_update == 0:
                raise ValidationError("The estimation is not open anymore.")
            for estimation_id in to_update:
                estimation_id.update_activity_block_btn()
        return res

    @api.depends('employee_id')
    def _compute_contract(self):
        for _id in self:
            contract_id = self.env['hr.contract'].search([('employee_id', '=', _id.employee_id.id),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            _id.contract_id = contract_id.id if contract_id else None

    @api.depends('employee_id', 'final_end_date', 'contract_id.period_group_id')
    def _compute_period(self):
        for _id in self:
            period_group_id = _id.contract_id.period_group_id.id
            period_id = self.env['payment.period'].search([('group_id', '=', period_group_id),
                                                           ('to_date', '>=', _id.final_end_date),
                                                           ('from_date', '<=', _id.final_end_date)])
            if period_id:
                _id.period_id = period_id.id

    @api.depends('final_start_date', 'block_origin')
    def _compute_sequence(self):
        for r in self:
            daily_blocks = self.search([('block_origin', 'in', ('calendar', 'extra')),
                                        ('employee_id', '=', r.employee_id.id),
                                        ('final_start_date', '>=', r.final_start_date.replace(hour=0, minute=0,
                                                                 second=1, microsecond=1)),
                                        ('final_end_date', '<=', r.final_start_date.replace(hour=23, minute=59,
                                                                 second=59, microsecond=1))], order='final_start_date ASC')
            sequence = 1
            for block_id in daily_blocks:
                if block_id.id == r.id:
                    break
                sequence += 1
            r.sequence = sequence

    def unlink(self):
        for block_id in self:
            if block_id.incidence_id:
                raise ValidationError(_('Cannot remove a block with a incidence.'))
            if self.env['mrp.workcenter.productivity'].search([('final_start_date', '>=', block_id.final_start_date),
                                                               ('final_start_date', '<=', block_id.final_start_date)]):
                raise ValidationError(_('Cannot remove a block with inputs.'))
        super(HrproductivityBlock, self).unlink()

    def start_activity(self, workcenter_ids, wanted_date=datetime.datetime.now(), validate_time=True):
        for workcenter_id in self.env['mrp.workcenter'].browse(workcenter_ids):
            self.generate_blocks(wanted_date, workcenter_id, validate_time=validate_time)
            # self.rebuild_blocks(workcenter_id.employee_id)

    def rebuild_blocks(self, employee_id):
        # Datetime is in UTC
        Blocks = self.env['hr.productivity.block']
        block_ids = Blocks.search([('employee_id', '=', employee_id.id),
                                   ('incidence_id', '!=', False)], order='final_start_date ASC')
        current_date = self._get_tz_datetime(datetime.now(), employee_id.user_id)
        for block_id in block_ids:
            incidence_start = block_id.final_start_date
            incidence_end = block_id.final_end_date

            if incidence_start.strftime('%Y-%m-%d') <= current_date.strftime('%Y-%m-%d'):
                min_date = incidence_start.replace(hour=00, minute=00, second=1)
                max_date = incidence_start.replace(hour=23, minute=59, second=59)

                day_block_ids = Blocks.search([('employee_id', '=', employee_id.id),
                                               ('final_start_date', '>=', min_date.strftime("%Y-%m-%d")),
                                               ('final_start_date', '<=', max_date.strftime("%Y-%m-%d")),
                                               ('incidence_id', '=', False)])

                if day_block_ids:
                    for day_block_id in day_block_ids:
                        day_block_start = day_block_id.final_start_date
                        day_block_end = day_block_id.final_end_date
                        #                   |----I----|                       INCIDENCE BLOCK
                        #                   |----B----|                       CASE 1
                        #                         |----B----|                 CASE 2
                        #             |----B----|                             CASE 3
                        #            |-----------B----------|                 CASE 4
                        #                     |--B--|                         CASE 5

                        # CASE 1
                        if incidence_start == day_block_start and incidence_end == day_block_end:
                            children_block_ids = Blocks.search([('parent_id', '=', day_block_id.id)])
                            children_block_ids.write({'parent_id': block_id.id})
                            block_id.write({'parent_id': day_block_id.parent_id.id})
                            day_block_id.unlink()

                        # CASE 2
                        elif day_block_start < incidence_start <= day_block_end <= incidence_end:
                            block_id.write({'parent_id': day_block_id.id})
                            day_block_id.write({'offset_end_date': incidence_start})

                        # CASE 3
                        elif day_block_end > incidence_end >= day_block_start >= incidence_start:
                            day_block_id.write({'offset_start_date': incidence_end,
                                                'parent_id': block_id.id})

                        # CASE 4
                        elif day_block_start < incidence_start <= incidence_end < day_block_end:
                            children_block_ids = Blocks.search([('parent_id', '=', day_block_id.id)])
                            children_block_ids.write({'parent_id': None})
                            day_block_id.write({'offset_end_date': incidence_start})
                            block_id.write({'parent_id': day_block_id.id})
                            new_block_id = Blocks.create({'start_date': incidence_end,
                                                          'end_date': day_block_end,
                                                          'employee_id': employee_id.id,
                                                          'block_type': day_block_id.block_type,
                                                          'block_origin': day_block_id.block_origin,
                                                          'parent_id': block_id.id})
                            children_block_ids.write({'parent_id': new_block_id.id})

                        # CASE 5
                        elif incidence_start <= day_block_start <= day_block_end <= incidence_end:
                            if day_block_id.parent_id:
                                block_id.write({'parent_id': day_block_id.id})
                            children_block_id = Blocks.search([('parent_id', '=', day_block_id.id)], limit=1)
                            if children_block_id:
                                children_block_end = children_block_id.final_end_date
                                if children_block_end == incidence_end:
                                    children_block_ids = Blocks.search([('parent_id', '=', children_block_id.id)])
                                    children_block_ids.write({'parent_id': block_id.id})
                            day_block_id.unlink()

    def modify_delay_blocks(self, employee_id, reference_date, user, set_fixed):
        contract_id = self.env['hr.contract'].search([('employee_id', '=', employee_id.id),
                                                      ('state', 'in', ['open', 'pending'])], limit=1)
        if contract_id:
            desired_group_name = self.env['res.groups'].search([('name', '=', 'TimeTracking Supervisor')])
            supervisor = user.id in desired_group_name.users.ids
            if contract_id.modify_delay or supervisor:
                start_day = reference_date.replace(hour=0, minute=0, second=0)
                end_day = reference_date.replace(hour=23, minute=59, second=59)
                block_delay_ids = self.search([('employee_id', '=', employee_id.id),
                                               ('start_date', '>=', start_day.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
                                               ('end_date', '<=', end_day.strftime(DEFAULT_SERVER_DATETIME_FORMAT)),
                                               ('block_origin', '=', 'delay')])
            for block_delay_id in block_delay_ids:
                block_delay_id.fixed_duration = None if set_fixed is False else block_delay_id.duration

    @api.depends('block_type', 'block_origin', 'sequence')
    def _compute_name(self):
        for _id in self:
            start_date = self.env['time.tracking.actions'].get_tz_datetime(_id.final_start_date, self.env.user)
            end_date = self.env['time.tracking.actions'].get_tz_datetime(_id.final_end_date, self.env.user)
            if _id.block_origin in ('calendar', 'extra'):
                name = 'Block {} ({})'.format(_id.sequence, start_date.strftime('%H:%M'))
            else:
                name = '{}.{}({}) {} to {}'.format(_id.block_type, _id.block_origin,
                                                   start_date.strftime('%a%d'),
                                                   start_date.strftime('%H:%M'),
                                                   end_date.strftime('%H:%M'))
            _id.name = name

    @api.depends('final_start_date')
    def _compute_dayofweek(self):
        for r in self:
            _start = r.final_start_date
            _date = self._get_tz_datetime(_start, r.employee_id.user_id)
            r.dayofweek = str(_date.weekday())

    @api.depends('offset_start_duration', 'offset_end_duration', 'start_date', 'end_date')
    def _compute_offset_date(self):
        for _id in self:
            _id.offset_start_date = _id.start_date - timedelta(minutes=_id.offset_start_duration) if _id.offset_start_duration else None
            _id.offset_end_date = _id.end_date + timedelta(minutes=_id.offset_end_duration) if _id.offset_end_duration else None

    @api.depends('start_date', 'offset_start_date', 'end_date', 'offset_end_date')
    def _compute_final_date(self):
        for _id in self:
            _id.final_start_date = _id.offset_start_date if _id.offset_start_date else _id.start_date
            _id.final_end_date = _id.offset_end_date if _id.offset_end_date else _id.end_date

    @api.depends('final_start_date', 'final_end_date')
    def _compute_duration(self):
        for r in self:
            if r.final_end_date:
                diff = fields.Datetime.from_string(r.final_end_date) - fields.Datetime.from_string(
                    r.final_start_date)
                duration = round(diff.total_seconds() / 60.0, 2)
                r.duration = duration if duration > 0.0 else 0.0
            else:
                r.duration = 0.0

    def write(self, vals):
        if 'stop_write_recursion' not in self.env.context:
            if 'offset_start_date' in vals:
                for _id in self:
                    if _id.parent_id:
                        _id.parent_id.with_context(stop_write_recursion=1).write(
                            {'offset_end_date': vals.get('offset_start_date')})
            if 'offset_end_date' in vals:
                for _id in self:
                    block_ids = self.env['hr.productivity.block'].search([('parent_id', '=', _id.id)])
                    for block_id in block_ids:
                        block_id.with_context(stop_write_recursion=1).write(
                            {'offset_start_date': vals.get('offset_end_date')})
        return super(HrproductivityBlock, self).write(vals)

    def unlink(self):
        for block_id in self:
            start = self.env['mrp.workcenter.productivity'].search([('final_start_date', '>=', block_id.final_start_date),
                                                                    ('final_start_date', '<=', block_id.final_end_date),
                                                                    ('employee_id', '=', block_id.employee_id.id)])
            end = self.env['mrp.workcenter.productivity'].search([('final_end_date', '>=', block_id.final_start_date),
                                                                   ('final_end_date', '<=', block_id.final_end_date),
                                                                   ('employee_id', '=', block_id.employee_id.id)])
            if start or end:
                raise ValidationError(_('Cannot remove a block with tracking record(s)'))
        super(HrproductivityBlock, self).unlink()

    @api.constrains('duration')
    def _check_duration(self):
        for _id in self:
            if _id.block_type == 'inactive' and _id.block_origin == 'timeoff' and _id.duration < _id.fixed_duration:
                raise ValidationError("The duration wanted ({} minutes) of the Calendar TimeOff Block(s) is "
                                      "less than minimum required({} minutes)".format(_id.duration, _id.fixed_duration))
            if _id.block_type == 'inactive' and _id.block_origin == 'delay' and _id.duration < _id.fixed_duration:
                raise ValidationError(
                    "The duration of the Delay block(id={}) cannot be less than"
                    " {} minutes".format(_id.id, _id.fixed_duration))
            if _id.duration <= 0:
                raise ValidationError("The block {} has a negative duration ({}).".format(_id.id, _id.duration))

    @api.constrains('final_end_date')
    def _check_end(self):
        for _id in self:
            start = _id.final_start_date
            end = _id.final_end_date
            tz_start = self.env['time.tracking.actions'].get_tz_datetime(start, _id.employee_id.user_id)
            tz_end = self.env['time.tracking.actions'].get_tz_datetime(end, _id.employee_id.user_id)
            if tz_start.weekday() != tz_end.weekday():
                raise ValidationError("The block {} can not start and end in a different day.".format(_id.id))

            if _id.offset_end_date and not self.env.user.has_group('aci_estimation.group_estimation_chief'):
                if _id.status == 'closed':
                    raise ValidationError("The Block {} is closed and can not be modified.".format(_id.id))
                end = _id.offset_end_date
                tz_end = self.env['time.tracking.actions'].get_tz_datetime(end, _id.employee_id.user_id)
                contract_id = self.env['hr.contract'].search([('employee_id', '=', _id.employee_id.id),
                                                              ('state', 'in', ['open', 'pending'])], limit=1)
                if contract_id:
                    attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                        .filtered(lambda r: int(r.dayofweek) == int(tz_end.weekday()))

                    hour_to = 0.0
                    for attendance_id in attendance_ids:
                        if attendance_id.hour_to > hour_to:
                            hour_to = attendance_id.hour_to

                    to_hour = int('{0:02.0f}'.format(*divmod(hour_to * 60, 60)))
                    to_minutes = int('{1:02.0f}'.format(*divmod(hour_to * 60, 60)))
                    block_end = tz_end.replace(hour=to_hour, minute=to_minutes, second=0)
                    if tz_end > (block_end + timedelta(minutes=contract_id.tolerance_time)) \
                            and contract_id.tolerance == 'restrictive':
                        has_parent = self.search([('parent_id', '=', _id.id)])
                        if not has_parent:
                            raise ValidationError("The employee {} has a restrictive contract."
                                                  " The Offset End date of the last block of the "
                                                  "day can not be greater than "
                                                  "the default date plus tolerance ({})".format(_id.employee_id.name,
                                                                                                block_end + timedelta(
                                                                                                    minutes=contract_id.tolerance_time)))
    def move_tracking(self, employee_id, range_start, range_end):
        employee_args = ('employee_id', '=', employee_id.id)
        str_range_start = range_start.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        str_range_end = range_end.strftime(DEFAULT_SERVER_DATETIME_FORMAT)
        # CASE 1: Tracking inside range = Delete
        del_tracking_ids = self.env['mrp.workcenter.productivity'].search([('final_start_date', '>=', str_range_start),
                                                                           ('final_start_date', '<=', str_range_end),
                                                                           ('final_end_date', '>=', str_range_start),
                                                                           ('final_end_date', '<=', str_range_end),
                                                                           employee_args])
        del_tracking_ids.unlink()
        # CASE 2: Start before range start = Change End
        sta_tracking_ids = self.env['mrp.workcenter.productivity'].search([('final_start_date', '<', str_range_start),
                                                                           ('final_end_date', '>', str_range_start),
                                                                           employee_args])
        sta_tracking_ids.write({'offset_end_date': range_start})
        # CASE 3: Start after range start = Change Start
        end_tracking_ids = self.env['mrp.workcenter.productivity'].search([('final_start_date', '>=', str_range_start),
                                                                           ('final_start_date', '<', str_range_end),
                                                                           ('final_end_date', '>', str_range_end),
                                                                           employee_args])
        end_tracking_ids.write({'offset_start_date': range_end})

    def end_activity(self, workcenter_ids, date_end=None):
        date_now = datetime.datetime.now() if not date_end else date_end
        for workcenter_id in self.env['mrp.workcenter'].browse(workcenter_ids):
            self.split_block(date_now, workcenter_id.employee_id, 'inactive', 'incidence')

    def lock_block(self, context=None):
        self.status = 'closed'

    def button_close_block(self, context=None):
        context = self.env.context
        self.browse(context.get('active_ids')).write({'status': 'closed'})

    # Datetime tools
    def _get_tz_datetime(self, datetime, user_id):
            Params = self.env['ir.config_parameter']
            tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
            tz = Params.get_param('tz') if tz_param else None
            if tz:
                tz_datetime = datetime.astimezone(pytz.timezone(str(tz)))
            else:
                user_id = user_id if user_id else self.env.user
                tz = str(user_id.tz) if user_id.tz else 'Mexico/General'
                tz_datetime = datetime.astimezone(pytz.timezone(tz))
            return tz_datetime

    def _remove_tz_datetime(self, datetime, user_id):
            Params = self.env['ir.config_parameter']
            tz_param = self.env['ir.config_parameter'].search([('key', '=', 'tz')])
            user_id = user_id if user_id else self.env.user
            tz = Params.get_param('tz') if tz_param else user_id.tz
            tz = tz if tz else 'Mexico/General'
            return pytz.timezone(tz).localize(datetime.replace(tzinfo=None), is_dst=False).astimezone(
                pytz.UTC).replace(tzinfo=None)

    def _get_float_hour(self, date):
        return float('{0}.{1}'.format(date.hour, date.minute))

    def generate_blocks(self, wanted_datetime, workcenter_id, basic_type='active', split=None, origin='calendar',
                        validate_time=True, _employee_id=None, block_available=True, warehouse_id=None):
        # datetime and split are in UTC
        Blocks = self.env['hr.productivity.block']

        if _employee_id:
            employee_id = _employee_id
        else:
            employee_id = workcenter_id.employee_id
        user_id = employee_id.user_id if employee_id.user_id else self.env.user
        current_date = self._get_tz_datetime(wanted_datetime, user_id)
        weekday = current_date.weekday()
        # 1. Check if the blocks are created (not generated by some incidence)
        block_ids = Blocks.search([('employee_id', '=', employee_id.id),
                                   ('block_type', '=', 'active'),
                                   ('incidence_id', '=', False)])
        today_blocks = False
        for _ids in block_ids:
            _start = _ids.final_start_date
            _date = self._get_tz_datetime(_start, employee_id.user_id)
            if _date.strftime("%Y-%m-%d") == current_date.strftime("%Y-%m-%d"):
                today_blocks = True
                break
        if not today_blocks or basic_type == 'inactive':
            contract_id = self.env['hr.contract'].search([('employee_id', '=', employee_id.id),
                                                          ('state', 'in', ['open', 'pending'])], limit=1)
            if contract_id:
                # 2. Get blocks to be created
                if _employee_id:
                    attendance_ids = contract_id.resource_calendar_id.attendance_ids \
                        .filtered(lambda r: int(r.dayofweek) == int(weekday))
                else:
                    attendance_ids = workcenter_id.resource_calendar_id.attendance_ids \
                        .filtered(lambda r: int(r.dayofweek) == int(weekday))
                blocks_to_create = []
                first_block = True
                for attendance_id in attendance_ids:
                    tolerance = abs(contract_id.tolerance_time)
                    contract_type = contract_id.tolerance
                    from_hour = int('{0:02.0f}'.format(*divmod(attendance_id.hour_from * 60, 60)))
                    from_minutes = int('{1:02.0f}'.format(*divmod(attendance_id.hour_from * 60, 60)))
                    to_hour = int('{0:02.0f}'.format(*divmod(attendance_id.hour_to * 60, 60)))
                    to_minutes = int('{1:02.0f}'.format(*divmod(attendance_id.hour_to * 60, 60)))

                    start = current_date.replace(hour=from_hour, minute=from_minutes, second=0)
                    end = current_date.replace(hour=to_hour, minute=to_minutes, second=0)

                    opposite_type = False
                    if validate_time:
                        if contract_type == 'restricted':
                            if start <= current_date <= (start + timedelta(minutes=tolerance)):
                                start = current_date
                            elif (start - timedelta(minutes=tolerance)) <= current_date <= start:
                                start = current_date
                            elif (start + timedelta(minutes=tolerance)) < current_date <= end and origin == 'calendar':
                                fixed_duration = abs(round((current_date - start).total_seconds() / 60.0, 2))
                                blocks_to_create.append((self._remove_tz_datetime(start, user_id),
                                                       self._remove_tz_datetime(current_date, user_id), None,
                                                       'inactive', fixed_duration, None, 'delay', None))
                                start = current_date
                            elif current_date >= end:
                                opposite_type = True
                        else:
                            if current_date < start and first_block:
                                incidence_id = self.env['attendance.incidence'].create({'check_in': current_date,
                                                                                        'check_out': start,
                                                                                        'employee_id': employee_id.id,
                                                                                        'name': 'Work Out of Schedule',
                                                                                        'productivity_block': False,
                                                                                        'type_incidence': 'work_out_schedule'})
                                blocks_to_create.append((self._remove_tz_datetime(current_date, user_id),
                                                         self._remove_tz_datetime(start, user_id), attendance_id.id,
                                                         'active', None, tolerance, 'extra', incidence_id.id))
                                start = current_date

                    utc_start = self._remove_tz_datetime(start, user_id)
                    utc_end = self._remove_tz_datetime(end, user_id)

                    if opposite_type:
                        if basic_type == 'active':
                            type = 'inactive'
                        elif basic_type == 'inactive':
                            type = 'active'
                        elif basic_type == 'timeoff':
                            type = 'inactive'
                    else:
                        type = basic_type
                    if split and utc_start <= split <= utc_end:
                        blocks_to_create.append((utc_start, split, attendance_id.id, type, None, tolerance, 'incidence', None))
                        break
                    first_block = False
                    blocks_to_create.append((utc_start, utc_end, attendance_id.id, type, None, tolerance, origin, None))

                blocks_to_create.sort(key=lambda x: (x[0]))
                # Generate Inactive Blocks the numbers of inactives is n-1 where n is the total of blocks
                for inactive in range(1, len(blocks_to_create)):
                    if round((blocks_to_create[inactive][0] - blocks_to_create[inactive - 1][
                                                 1]).total_seconds() / 60.0, 2) >= 1:
                        type = 'timeoff' if origin == 'calendar' else origin
                        blocks_to_create.append((blocks_to_create[inactive - 1][1],
                                                 blocks_to_create[inactive][0],
                                                 None, 'inactive',
                                                 round((blocks_to_create[inactive][0] - blocks_to_create[inactive - 1][
                                                     1]).total_seconds() / 60.0, 2), None, type, None))

                blocks_to_create.sort(key=lambda x: (x[0]))
                parent_id = None
                for block in blocks_to_create:
                    block_id = Blocks.create({'start_date': block[0],
                                              'end_date': block[1],
                                              'employee_id': employee_id.id,
                                              'resource_calendar_attendance_id': block[2],
                                              'block_type': block[3],
                                              'fixed_duration': block[4],
                                              'block_origin': block[6],
                                              'incidence_id': block[7],
                                              'block_available': block_available,
                                              'warehouse_id': warehouse_id,
                                              'parent_id': parent_id})
                    parent_id = block_id.id
        else:
            if origin == 'calendar':
                self.split_block(wanted_datetime, employee_id, 'active', 'calendar')

    def split_block(self, datetime, employee_id, type, origin):
        #  Datetime is in UTC
        Blocks = self.env['hr.productivity.block']
        current_date = self._get_tz_datetime(datetime, employee_id.user_id)
        block_ids = Blocks.search([('employee_id', '=', employee_id.id)])

        today_block_ids = []
        for block_id in block_ids:
            _start = block_id.final_start_date
            _date = self._get_tz_datetime(_start, employee_id.user_id)
            if _date.strftime("%Y-%m-%d") == current_date.strftime("%Y-%m-%d"):
                today_block_ids.append(block_id)

        for block_id in today_block_ids:
            start = self._get_tz_datetime(block_id.final_start_date, employee_id.user_id)
            end = self._get_tz_datetime(block_id.final_end_date, employee_id.user_id)
            if start <= current_date <= end:
                split_block_id = Blocks.create({'start_date': datetime,
                                                'end_date': block_id.final_end_date,
                                                'employee_id': employee_id.id,
                                                'block_type': type,
                                                'block_origin': origin})
                child_block_ids = Blocks.search([('parent_id', '=', block_id.id)])
                child_block_ids.write({'parent_id': split_block_id.id})
                split_block_id.write({'parent_id': block_id.id})
                block_id.write({'offset_end_date': datetime})
            if start > current_date:
                final_origin = 'timeoff' if type == 'active' and block_id.fixed_duration > 0 else origin
                final_type = 'inactive' if type == 'active' and block_id.fixed_duration > 0 else type
                block_id.write({'block_type': final_type,
                                'block_origin': final_origin})

    def generate_specific_block(self, start_date, end_date, employee_id, basic_type='active', origin='calendar'):
        Blocks = self.env['hr.productivity.block']

        # Look for existing blocks
        bigger_blocks = Blocks.search([('employee_id', '=', employee_id.id),
                                       ('start_date', '<=', start_date),
                                       ('end_date', '>=', end_date)])
        contained_blocks = Blocks.search([('employee_id', '=', employee_id.id),
                                          ('start_date', '>=', start_date),
                                          ('end_date', '<=', end_date)])
        ending_blocks = Blocks.search([('employee_id', '=', employee_id.id),
                                       ('start_date', '>=', start_date),
                                       ('start_date', '<=', end_date),
                                       ('end_date', '>=', end_date)])
        started_blocks = Blocks.search([('employee_id', '=', employee_id.id),
                                       ('start_date', '<=', start_date),
                                       ('end_date', '>=', start_date),
                                       ('end_date', '<=', end_date)])
        if bigger_blocks or contained_blocks or ending_blocks or started_blocks:
            raise ValidationError(
                "{} already has activity Blocks at that time.".format(employee_id.name))

        Blocks.create({'start_date': start_date,
                       'end_date': end_date,
                       'employee_id': employee_id.id,
                       'block_type': basic_type,
                       'block_origin': origin})

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
                        'default_int_result': res_value}
        }

    def show_offset_start_date_calculator_btn(self, context=None):
        return self.show_calculator('hr.productivity.block', 'offset_start_duration', self.id, self.offset_start_duration, 'float')

    def show_offset_end_date_calculator_btn(self, context=None):
        return self.show_calculator('hr.productivity.block', 'offset_end_duration', self.id, self.offset_end_duration, 'float')

    def show_productivity_btn(self):
        Productivity = self.env['mrp.workcenter.productivity']
        view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_timeline')
        tree_view_id = self.env['ir.model.data'].get_object(
            'aci_estimation', 'mrp_workcenter_productivity_estimation_tree_view')

        search_args = [('employee_id', '=', self.employee_id.id),
                       ('timetracking_id', '!=', False),
                       ('date_start', '>=', self.final_start_date),
                       ('date_end', '>=', self.final_end_date)]

        _ids = Productivity.search(search_args)
        return {
            'type': 'ir.actions.act_window',
            'views': [(tree_view_id.id, 'tree'), (view_id.id, 'timeline')],
            'view_mode': 'form,timeline',
            'name': 'Tracking Log',
            'res_model': 'mrp.workcenter.productivity',
            'target': 'current',
            'domain': [('id', 'in', _ids.ids)]
        }
