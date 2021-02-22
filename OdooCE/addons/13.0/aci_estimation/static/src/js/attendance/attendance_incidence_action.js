odoo.define('aci_estimation.AttendanceIncidenceActions', (require) => {
    'use strict';

    var core = require('web.core');
    var framework = require('web.framework');
    var rpc = require('web.rpc');

    class AttendanceIncidence {
        constructor(parent, action) {
            this.action = action;
            this.context = action.context;
        }

        approveIncompleteAttendanceLog() {
            var attLogDates = this.context.attendance_log_dates.sort(),
                employeeId = this.context.employee_id,
                newAttendance = this._getAttendanceFromAttLogDateSet(attLogDates, employeeId);

            this._saveAttendance(newAttendance);
        }

        _saveAttendance(newRecords) {
            var self = this;

            rpc.query({
                model: 'hr.attendance',
                method: 'save_massive_attendance',
                args: [newRecords, []]
            }).then(() => {
                self.reload();
            });
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

        _getAttendanceFromAttLogDateSet(attLogDates, employeeId) {
            var check_in = this._getDateFromUTC(attLogDates.splice(0, 1)[0]),
                check_out = this._getDateFromUTC(attLogDates.splice(0, 1)[0]),
                inserts = [this._getAttendanceInsert(employeeId, check_in, check_out)];

            if (attLogDates.length)
                inserts = inserts.concat(this._getAttendanceFromAttLogDateSet(attLogDates, employeeId));

            return inserts;
        }

        _getDateFromUTC(stringUTCDate) {
            var stringLocalDate = moment.utc(stringUTCDate).local().format('YYYY-MM-DD HH:mm:ss');
            return new Date(stringLocalDate);
        }

        _getStringDayFromDate(date) {
            var dayMap = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday',
                'Friday', 'Saturday'];
            return dayMap[date.getDay()];
        }

        _getFloatHourFromDate(date) {
            var hours = date.getHours(),
                minutes = date.getMinutes() / 60;
            return parseFloat((hours + minutes).toFixed(2));
        }

        _getAttendanceInsert(employeeId, check_in, check_out) {
            return {
                employee_id: employeeId,
                check_in: check_in,
                check_out: check_out,
                date_computed: moment(check_in).format('YYYY-MM-DD'),
                day_computed: this._getStringDayFromDate(check_in),
                check_in_hour: this._getFloatHourFromDate(check_in),
                check_out_hour: this._getFloatHourFromDate(check_out)
            }
        }
    }

    var ApproveIncompleteAttendanceLog = (parent, action) => {
        var AttIncidence = new AttendanceIncidence(parent, action);
        AttIncidence.approveIncompleteAttendanceLog();
    };

    core.action_registry.add('approve_incomplete_attendance_log', ApproveIncompleteAttendanceLog);
});
