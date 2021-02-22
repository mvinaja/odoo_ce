odoo.define('aci_estimation.AttendanceLogActions', (require) => {
    'use strict';

    var core = require('web.core');
    var framework = require('web.framework');
    var rpc = require('web.rpc');
    var Context = require('web.Context');
    var field_utils = require('web.field_utils');

    class AttendanceLog {
        constructor(parent, action) {
            this.action = action;
            this.context = action.context;
        }

        import() {
            var new_records = this._getRecordsToImport();
            if (new_records && new_records.length)
                this._callMethodModel('save_massive_attendance_log', this.reload.bind(this), [new_records]);
            else
                this.reload();
        }

        generateMassiveLogs() {
            var hour = field_utils.parse.float_time(this.context.hour + ':' + this.context.minutes);
            var new_records = [];
            for (var employee_id of Object.keys(this.context.employee_schedule)) {
                if (this.context.date) {
                    new_records.push(this._getGeneratedLog(employee_id, this.context.date, hour));
                } else if (this.context.dayofweek) {
                    new_records = new_records.concat(this._getGeneratedLogsFilterDays(employee_id, hour));
                } else
                    new_records = new_records.concat(this._getGeneratedLogsAllDays(employee_id, hour));
            }

            new_records = new_records.filter(Boolean)
            if (new_records && new_records.length)
                this._callMethodModel('save_massive_attendance_log', this.reload.bind(this), [new_records]);
            else
                this.reload();
        }

        _callMethodModel(method, callback, args) {
            var context = this._getContextToSend(),
            query_definition = {
                model: 'attendance.log', // context.params.model,
                method: method,
                context: context
            };
            if (arguments[2])
                query_definition.args = arguments[2];

            rpc.query(query_definition).then(callback);
        }

        reload() {
            var params = this.action.params || {};
            var menu_id = params.menu_id || false;
            var l = window.location;

            var sobj = $.deparam(l.search.substr(1));
            if (params.url_search)
                sobj = _.extend(sobj, params.url_search);
            var search = '?' + $.param(sobj);

            var hash = l.hash;
            if (menu_id)
                hash = "#menu_id=" + menu_id;
            var url = l.protocol + "//" + l.host + l.pathname + search + hash;

            framework.redirect(url, params.wait);
        }

        _getContextToSend() {
            var context = JSON.parse(JSON.stringify(this.context));
            delete context.date_from;
            delete context.date_to;
            delete context.existing_records;
            delete context.new_records;
            var nContext = new Context(context);
            return nContext;
        }

        _getGeneratedLogsFilterDays(employee_id, float_hour) {
            var records = [];
            for (var date in this.context.date_range) {
                if (String(this.context.date_range[date]) == this.context.dayofweek)
                    records.push(this._getGeneratedLog(employee_id, date, float_hour));
            }
            return records;
        }

        _getGeneratedLogsAllDays(employee_id, float_hour) {
            var records = [];
            for (var date in this.context.date_range) {
                records.push(this._getGeneratedLog(employee_id, date, float_hour));
            }
            return records;
        }

        _getGeneratedLog(employee_id, date, float_hour) {
            if (this._isGeneratedLogValid(employee_id, date, float_hour)) {
                var days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday',
                        'Thursday', 'Friday', 'Saturday'],
                    nDate = date + ' ' + this.context.hour + ':' + this.context.minutes + ':00',
                    datetime = new Date(nDate);
                return {
                    attendance_log_date: datetime,
                    created_by_user: true,
                    date_computed: moment(datetime).format('YYYY-MM-DD'),
                    day_computed: days[datetime.getDay()],
                    hour_computed: datetime.getHours() + (datetime.getMinutes() / 60),
                    employee_id: employee_id
                };
            }

            return false;
        }

        _getRecordsToImport() {
            var date_from = this.context.date_from,
                date_to = this.context.date_to,
                existing_records = this.context.existing_records;

            return this.context.new_records.filter((record) => {
                var datetime = new Date(record.attendance_log_date),
                    str_date = moment(datetime).format('YYYY-MM-DD'),
                    utc_date = moment(datetime).utc().format('YYYY-MM-DD HH:mm:ss');

                return date_from <= str_date && str_date <= date_to
                       && existing_records.indexOf(record.employee_id + '--' + utc_date) < 0;
            }).map((record) => {
                var days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'],
                    datetime = new Date(record.attendance_log_date);
                    // date = _.str.sprintf('%02d', datetime.getDate());
                record.attendance_log_date = datetime;
                record.date_computed = moment(datetime).format('YYYY-MM-DD');
                record.day_computed = days[datetime.getDay()];
                record.hour_computed = datetime.getHours() + (datetime.getMinutes() / 60);
                return record;
            });
        }

        _isGeneratedLogValid(employee_id, date, hour) {
            var schedule = this.context.employee_schedule[employee_id],
                att_days = Object.keys(schedule),
                weekday = new Date(date).getDay();

            return att_days.indexOf(String(weekday)) != -1 && hour <= schedule[weekday][1];
        }
    }

    var ImportAttendanceLog = (parent, action) => {
        var AttLog = new AttendanceLog(parent, action);
        AttLog.import();
    },
    GenerateMassiveLogs = (parent, action) => {
        var AttLog = new AttendanceLog(parent, action);
        AttLog.generateMassiveLogs();
    };

    core.action_registry.add('import_attendance_log', ImportAttendanceLog);
    core.action_registry.add('generate_massive_logs', GenerateMassiveLogs);
});
