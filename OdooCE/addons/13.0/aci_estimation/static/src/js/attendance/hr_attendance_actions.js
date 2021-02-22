odoo.define('aci_estimation.HrAttendanceActions', (require) => {
    'use strict';

    var core = require('web.core');
    var framework = require('web.framework');
    var rpc = require('web.rpc');

    class HrAttendance {
        constructor(parent, action) {
            this.action = action;
            this.context = action.context;
        }

        computeAttendance() {
            var att_logs = this.context.employee_attendance,
                records_to_delete = this.context.records_to_delete,
                inserts = {attendance: [], incidence: []};
            for (var employee_id of Object.keys(att_logs)) {
                var new_log_dates = this._orderAttendanceLogsByDate(att_logs[employee_id]);
                att_logs[employee_id].log_dates = new_log_dates;
                var n_inserts = this._getInsertsFromCompute(employee_id, att_logs[employee_id]);
                this._removeTimeFromScheduleLeave(n_inserts, att_logs[employee_id].schedule.schedule_leave)
                inserts.attendance = inserts.attendance.concat(n_inserts.attendance);
                inserts.incidence = inserts.incidence.concat(n_inserts.incidence);
            }
            this._saveIncidence(inserts, records_to_delete);
        }

        _saveIncidence(newRecords, recordsToDelete) {
            var self = this;

            rpc.query({
                model: 'attendance.incidence',
                method: 'save_massive_incidence',
                args: [newRecords.incidence, recordsToDelete.incidence]
            }).then(() => {
                self._saveAttendance(newRecords.attendance, recordsToDelete.attendance);
            });
        }

        _saveAttendance(newRecords, recordsToDelete) {
            var self = this;

            rpc.query({
                model: 'hr.attendance',
                method: 'save_massive_attendance',
                args: [newRecords, recordsToDelete]
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

        _orderAttendanceLogsByDate(employee_att_logs) {
            var log_dates = employee_att_logs.log_dates, days = {};
            for (var log_date of log_dates) {
                var local_datetime_str = moment.utc(log_date).local().format('YYYY-MM-DD HH:mm:ss'),
                    datetime_obj = new Date(local_datetime_str),
                    date_str = moment(datetime_obj).format('YYYY-MM-DD');
                if (!days[date_str])
                    days[date_str] = {'weekday': (datetime_obj.getDay() + 6) % 7, 'dates': []};

                days[date_str].dates.push(datetime_obj);
            }
            return Object.values(days);
        }

        _removeTimeFromScheduleLeave(inserts, schedule_leave) {
            this._removeTimeFromAttendance(inserts.attendance, schedule_leave);
            this._removeTimeFromIncidence(inserts.incidence, schedule_leave);
        }

        _removeTimeFromAttendance(attendance, schedule_leave) {
            for (var att of attendance) {
                if (schedule_leave[att.weekday])
                    this._removeTimeFromDay(attendance, att, schedule_leave[att.weekday]);
                delete att.weekday;
            }
        }

        _removeTimeFromIncidence(incidence, schedule_leave) {
            for (var inc of incidence) {
                if (inc.type_incidence == 'work_out_schedule' && schedule_leave[inc.weekday])
                    this._removeTimeFromDay(incidence, inc, schedule_leave[inc.weekday]);
                delete inc.weekday;
            }
        }

        _removeTimeFromDay(dataSet, record, schedule_leave_day) {
            for (var block_schedule of schedule_leave_day) {
                var idx = dataSet.indexOf(record);

                // Si el inicio del horario de ausencia (block_schedule[0]) es menor o igual
                // al check_in del empleado y el fin del horario de ausencia
                // (block_schedule[1]) es mayor o igual al check_out del empleado. el horario
                // de ausencia abarca todo el registro tiempo (check_in - check_out)
                // por lo tanto se debera eliminar el registro de tiempo.
                if (block_schedule[0] <= record.check_in_hour && block_schedule[1] >= record.check_out_hour) {
                    dataSet.splice(idx, 1);

                // Si el inicio del horario de ausencia (block_schedule[0]) es mayor o igual
                // al check_in del empleado y el fin del horario de ausencia
                // (block_schedule[1]) es menor o igual al check_out del empleado. el horario
                // de ausencia esta dentro del registro de tiempo (check_in - check_out)
                // por lo tanto se debera dividir en dos rigistros de tiempo para dejar libre
                // el bloque de horario de ausencia.
                } else if (block_schedule[0] >= record.check_in_hour && block_schedule[1] <= record.check_out_hour) {
                    if (record.check_out_hour - block_schedule[1] > 0.01) {
                        var check_in = record.check_in, check_out = record.check_out,
                            cp_record = JSON.parse(JSON.stringify(record));
                        cp_record.check_in_hour = parseFloat(block_schedule[1].toFixed(2));
                        cp_record.check_in = this._getDateTimeForInsert(check_in, block_schedule[1]);
                        cp_record.check_out = check_out;
                        dataSet.splice(idx + 1, 0, cp_record);
                    }
                    if (block_schedule[0] - record.check_in_hour > 0.01) {
                        record.check_out_hour = parseFloat(block_schedule[0].toFixed(2));
                        record.check_out = this._getDateTimeForInsert(record.check_out, block_schedule[0]);
                    } else
                        dataSet.splice(idx, 1);

                // Si el fin del horario de ausencia (block_schedule[1]) es mayor que el
                // check_in y el fin del horario de ausencia es menor o igual al check_out.
                // El fin del horario de ausencia se encuentra dentro del registro de tiempo
                // trabajado (check_in - check_out) por lo tanto se debera de ajustar el
                // check_in para dejar fuera el horario de ausencia.
                } else if (block_schedule[1] > record.check_in_hour && block_schedule[1] <= record.check_out) {
                    if (record.check_out_hour - block_schedule[1] > 0) {
                        record.check_in_hour = parseFloat(block_schedule[1].toFixed(2));
                        record.check_in = this._getDateTimeForInsert(record.check_in, block_schedule[1]);
                    } else
                        dataSet.splice(idx, 1);

                // Si el inicio del horario de ausencia (block_schedule[0]) es mayor o igual
                // que el check_in y el inicio del horario de ausencia es menor que el
                // check_out. El inicio del horario de ausencia se encuentra dentro del
                // registro de tiempo trabajado (check_in - check_out) por lo tanto se
                // debera de ajustar el check_out para dejar fuera el horario de ausencia.
                } else if (block_schedule[0] >= record.check_in_hour && block_schedule[0] < record.check_out) {
                    if (block_schedule[0] - record.check_in_hour > 0) {
                        record.check_out_hour = parseFloat(block_schedule[0].toFixed(2));
                        record.check_out = this._getDateTimeForInsert(record.check_out, block_schedule[0]);
                    } else
                        dataSet.splice(idx, 1);
                }
            }
        }

        _getInsertsFromCompute(employee_id, employee_att_logs) {
            var schedule = employee_att_logs.schedule,
                tolerance = employee_att_logs.tolerance,
                date_log_dates = employee_att_logs.log_dates,
                inserts = {attendance: [], incidence: []};

            for (var log_dates of date_log_dates) {
                var n_inserts = this._getInsertsFromDaySet(employee_id, schedule,
                    tolerance, log_dates.weekday, log_dates.dates, 0);
                inserts.attendance = inserts.attendance.concat(n_inserts.attendance);
                inserts.incidence = inserts.incidence.concat(n_inserts.incidence);
            }
            return inserts;
        }

        /**
         * Analyze attendance log dates made in a day.
         * Iterate (recursively) until doesn't exists date log in the set.
         */
        _getInsertsFromDaySet(employee_id, schedule, tolerance, weekday, dates, sequence) {
            if (dates.length == 1)
                return {
                    attendance: [],
                    incidence: [this._getIncidenceForMissDate(employee_id, dates[0], weekday)]
                };

            var end = dates.splice(1, 1)[0], start = dates.splice(0, 1)[0],
            // Get start and end hour in float format
            hour_start = start.getHours() + (start.getMinutes() / 60),
            hour_end = end.getHours() + (end.getMinutes() / 60);

            if (!(weekday in schedule.schedule_working)) {
                var args = ['Working on weekend', employee_id, start, weekday, hour_start, hour_end];
                return {
                    attendance: [],
                    incidence: [this._getIncidenceForWorkOutOfSchedule(...args)]
                };
            }


            var inserts = {attendance: [], incidence: []},
                schedule_day = schedule.schedule_working[weekday].sort((a, b) => {return a[0] - b[0]}),
                // Obtener tiempo de tolerancia (guardado en minutos) en formato flotante.
                tolerance_time = tolerance.type == 'restrictive' && (Math.abs(tolerance.time) / 60) || 0;

            // Obtener incidencias y attendance a partir de los registros de un empleado en un
            // dia con respecto a el horario de ese dia.
            var date = new Date(start.getTime());
            var n_inserts = this._getInsertsFromScheduleWorkDay(employee_id, schedule_day, date, weekday, hour_start, hour_end, tolerance_time);
            inserts.attendance = inserts.attendance.concat(n_inserts.attendance);
            inserts.incidence = inserts.incidence.concat(n_inserts.incidence);

            if (dates.length) {
                n_inserts = this._getInsertsFromDaySet(employee_id, schedule, tolerance,
                    weekday, dates, sequence++);
                inserts.attendance = inserts.attendance.concat(n_inserts.attendance);
                inserts.incidence = inserts.incidence.concat(n_inserts.incidence);
            }

            return inserts;
        }

        /**
         * Compara los registros del empleado en un dia contra el horario de trabajo.
         * - Horario de trabajo => Menu: Attendance -> Configuration -> Working Time;
         *                         Pestania: Working hours
         */
        _getInsertsFromScheduleWorkDay(employee_id, schedule_day, date, weekday, hour_start, hour_end, tolerance) {
            // count_schedule_blocks: blocks of schedule i.e.: in this schedule -> [[8.0, 14.0], [15.0, 17.5]]
            // are 2 blocks of schedule
            var count_schedule_blocks = 1, inserts = {attendance: [], incidence: []},
                pendin_hours = false;

            for (var schedule_block of schedule_day) {
                if (hour_start > schedule_block[1] && count_schedule_blocks < schedule_day)
                    continue;

                if (pendin_hours && pendin_hours.length) {
                    var args = [employee_id, date, weekday, pendin_hours[0], hour_end, tolerance, count_schedule_blocks, schedule_day.length].concat(schedule_block),
                        n_inserts = this._getInsertsFromScheduleBlock(...args);
                    pendin_hours = false;
                } else {
                    var args = [employee_id, date, weekday, hour_start, hour_end, tolerance, count_schedule_blocks, schedule_day.length].concat(schedule_block),
                        n_inserts = this._getInsertsFromScheduleBlock(...args);
                }
                inserts.attendance = inserts.attendance.concat(n_inserts.attendance);
                inserts.incidence = inserts.incidence.concat(n_inserts.incidence);

                if (n_inserts.pending_hours && count_schedule_blocks == schedule_day.length) {
                    args = ['Work after schedule', employee_id, date, weekday].concat(n_inserts.pending_hours);
                    inserts.incidence.push(this._getIncidenceForWorkOutOfSchedule(...args))
                } else if (n_inserts.pending_hours && count_schedule_blocks < schedule_day.length) {
                    pendin_hours = n_inserts.pending_hours;
                }

                count_schedule_blocks++;

                if (hour_end < schedule_block[0])
                    break;
            }

            return inserts;
        }

        _getInsertsFromScheduleBlock(employee_id, date, weekday, hour_start, hour_end, tolerance, count_schedule_blocks, total_schedule_blocks, schedule_start, schedule_end) {
            var pointer_hour = arguments[10] || hour_start,
                inserts = {attendance: [], incidence: []};

            // Si el puntero de hora (pointer_hour) es mayor a la hora de salida (schedule_end)
            // mas tolerancia y el puntero de hora es menor que la hora de checada final (hour_end).
            // Es superior al bloque de horario actual (schedule_start - schedule_end).
            // Poner horas como pendientes (pointer_hour - hour_end) y terminar recursividad.
            if (pointer_hour >= (schedule_end + tolerance) && pointer_hour < hour_end) {
                inserts.pending_hours = [pointer_hour, hour_end];
                return inserts;

            // Si el puntero de hora (pointer_hour) llego a la checada final (hour_end).
            // Terminar recursividad.
            } else if (pointer_hour >= hour_end) {
                return inserts;

            // Si el puntero de hora (pointer_hour) es menor que la hora de entrada (schedule_start)
            // menos tolerancia y la checada final (hour_end) es menor que la hora de entrada
            // (schedule_start). Es inferior al bloque de de horario actual (schedule_start - schedule_end).
            // Generar insidencia de trabajo fuera de horario y terminar recursividad.
            } else if (pointer_hour < (schedule_start - tolerance) && hour_end <= schedule_start + 0.017) {
                var incidence_name = count_schedule_blocks == 1 ? 'Work before schedule' : 'Work on meal schedule',
                    args = [incidence_name, employee_id, date, weekday, pointer_hour, hour_end];
                inserts.incidence.push(this._getIncidenceForWorkOutOfSchedule(...args));
                return inserts;

            // Si el puntero de hora (pointer_hour) es menor que la hora de entrada (schedule_start)
            // menos tolerancia y la checada final (hour_end) es mayor que la hora de entrada
            // (schedule_start). Parte del registro de trabajo (tiempo entre checadas) esta dentro
            // del bloque de horario actual (schedule_start - schedule_end). Crear insidencia de
            // la parte inferior a la hora de entrada menos tolerancia y mover el puntero de hora
            // sobre la hora de entrada menos tolerancia.
            } else if (pointer_hour < (schedule_start - tolerance) && hour_end > schedule_start) {
                if (count_schedule_blocks > 1) {
                    var incidence_name = 'Work on meal schedule',
                    args = [incidence_name, employee_id, date, weekday, pointer_hour, schedule_start];
                } else {
                    var incidence_name = 'Work before schedule',
                        args = [incidence_name, employee_id, date, weekday, pointer_hour, (schedule_start - tolerance)];
                }
                inserts.incidence.push(this._getIncidenceForWorkOutOfSchedule(...args));
                // Aumentar 0.01 (1 minuto) para que no se encime con el registro anterior
                // (por validacion de odoo).
                if (count_schedule_blocks > 1)
                    pointer_hour = schedule_start + 0.017;
                else
                    pointer_hour = schedule_start - tolerance + 0.017;

            // Si el puntero de hora (pointer_hour) es mayor o igual que la hora de entrada
            // (schedule_start) menos tolerancia y la checada final (hour_end) es menor o igual
            // a la hora de salida (schedule_end) mas tolerancia. Esta dentro del bloque de horario
            // actual (schedule_start - schedule_end). Crear registro de attendance para la hora
            // del puntero y la checada final y mover el puntero a checada final.
            } else if (pointer_hour >= (schedule_start - tolerance) && hour_end <= (schedule_end + tolerance + 0.017)) {
                inserts.attendance.push(this._getAttendanceInsert(employee_id, date, weekday, pointer_hour, hour_end));
                pointer_hour = hour_end;

            } else if (count_schedule_blocks < total_schedule_blocks && pointer_hour >= schedule_end) {
                inserts.pending_hours = [pointer_hour, hour_end];
                return inserts;

            // Si el puntero de hora (pointer_hour) es mayour o igual que la hora de entrada
            // (schedule_start) menos tolerancia y la checada final (hour_end) es mayor que la
            // hora de salida (schedule_end) mas tolerancia. Parte del registro de trabajo se
            // encuentra dentro del bloque de horario actual (schedule_start - schedule_end).
            // Crear registro de attendance para la hora del puntero y la hora de salida mas
            // tolerancia; mover puntero a hora de salida mas tolerancia.
            } else if (pointer_hour >= (schedule_start - tolerance) && hour_end > (schedule_end + tolerance + 0.017)) {
                if (count_schedule_blocks == total_schedule_blocks) {
                    inserts.attendance.push(this._getAttendanceInsert(employee_id, date, weekday, pointer_hour, (schedule_end + tolerance)));
                    // Aumentar 0.01 (1 minuto) para que no se encime con el registro anterior
                    // (por validacion de odoo).
                    pointer_hour = schedule_end + tolerance + 0.017;
                } else {
                    inserts.attendance.push(this._getAttendanceInsert(employee_id, date, weekday, pointer_hour, schedule_end));
                    // Aumentar 0.01 (1 minuto) para que no se encime con el registro anterior
                    // (por validacion de odoo).
                    pointer_hour = schedule_end + 0.017;
                }
            }

            var n_inserts = this._getInsertsFromScheduleBlock(employee_id, date, weekday, hour_start, hour_end, tolerance, count_schedule_blocks, total_schedule_blocks, schedule_start, schedule_end, pointer_hour)
            inserts.attendance = inserts.attendance.concat(n_inserts.attendance);
            inserts.incidence = inserts.incidence.concat(n_inserts.incidence);
            if (n_inserts.pending_hours) inserts.pending_hours = n_inserts.pending_hours;
            return inserts;
        }

        _getAttendanceInsert(employee_id, date, weekday, check_in_hour, check_out_hour) {
            return {
                employee_id: employee_id,
                check_in: this._getDateTimeForInsert(date, check_in_hour),
                check_out: this._getDateTimeForInsert(date, check_out_hour),
                date_computed: moment(date).format('YYYY-MM-DD'),
                day_computed: this._getStringDay(weekday),
                check_in_hour: parseFloat(check_in_hour.toFixed(2)),
                check_out_hour: parseFloat(check_out_hour.toFixed(2)),
                weekday: weekday
            }
        }

        _getIncidenceForMissDate(employee_id, log_date, weekday) {
            return {
                name: 'Only one log date',
                type_incidence: 'incomplete_logs',
                state: 'draft',
                employee_id: employee_id,
                is_computed: true,
                check_in: log_date,
                check_out: 'NULL',
                date_computed: moment(log_date).format('YYYY-MM-DD'),
                day_computed: this._getStringDay(weekday),
                check_in_hour: parseFloat((log_date.getHours() + (log_date.getMinutes() / 60)).toFixed(2)),
                check_out_hour: 'NULL'
            };
        }

        _getIncidenceForWorkOutOfSchedule(name, employee_id, date, weekday, check_in_hour, check_out_hour) {
            return {
                name: name,
                type_incidence: 'work_out_schedule',
                state: 'draft',
                employee_id: employee_id,
                is_computed: true,
                check_in: this._getDateTimeForInsert(date, check_in_hour),
                check_out: this._getDateTimeForInsert(date, check_out_hour),
                date_computed: moment(date).format('YYYY-MM-DD'),
                day_computed: this._getStringDay(weekday),
                check_in_hour: parseFloat(check_in_hour.toFixed(2)),
                check_out_hour: parseFloat(check_out_hour.toFixed(2)),
                weekday: weekday
            };
        }

        _getDateTimeForInsert(date, float_hour) {
            var n_date = new Date(date.getTime());
            n_date.setHours(parseInt(float_hour));
            n_date.setMinutes(parseInt((float_hour - parseInt(float_hour)) * 60));
            n_date.setSeconds(0);
            return n_date;
        }

        _getStringDay(weekday) {
            var days = ['Monday', 'Tuesday', 'Wednesday',
                    'Thursday', 'Friday', 'Saturday', 'Sunday'];
            return days[weekday];
        }
    }

    var ComputeAttendance = (parent, action) => {
        var HrAtt = new HrAttendance(parent, action);
        HrAtt.computeAttendance();
    };

    core.action_registry.add('compute_attendance', ComputeAttendance);
});
