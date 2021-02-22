odoo.define('aci_estimation.TimeTrackWorkflow', function (require) {
    'use strict';

    var core = require('web.core');
    var rpc = require('web.rpc');
    var Context = require('web.Context');
    var web_client = require('web.web_client');
    var Dialog = require('web.Dialog');

    var QWeb = core.qweb;
    var _t = core._t;
    var _lt = core._lt;

    class TimetrackingActions {
        constructor(modelName, renderer, controller) {
            this._modelName = modelName;
            this._renderer = renderer;
            this._controller = controller;
            this._record = false;
            this._originStage = false;
            this._targetStage = false;
            this._bool_task = false;
            this._selection = false;
        }

        _loadStageLabels(model,param) {
            var self = this;
            var modelName = this._modelName;
            var checked_ids = this.getSelectedItems('check-to-move');
            var selected_id = $(model.currentTarget).data('value');
            if (!checked_ids) {
                checked_ids = [selected_id];
            }
            else{
                if(!checked_ids.includes(selected_id)){checked_ids.push(selected_id);}
            }
            if(param=='todo'){
                self.move_to_stage(null, [selected_id], modelName, 'Working', 'ToDo', {});
            }
            if(param=='blocked'){
                self.move_to_stage(null, [selected_id], modelName, 'ToDo', 'Blocked', {});
            }
            if(param=='finished'){
                self.move_to_stage(null, [selected_id], modelName, 'ToDo', 'Finished', {});
            }
        }

       getGeoLocation(model) {
            var self = this;
            model.stopImmediatePropagation();
            model.preventDefault();
            var modelName = this._modelName;
            var selected_id = $(model.currentTarget).data('value');
            var employee_id = this._renderer.state.context['imputed_employee_id'];
            var lat = null;
            var long = null;
            if(this._renderer.state.context['selected_analytic_id'])
            {
                var analytic_id = this._renderer.state.context['selected_analytic_id'][0];

            }
            else{var analytic_id =null;}
            var options = { enableHighAccuracy: true, maximumAge: 100, timeout: 60000 };

            var device = $.ua.device.vendor +', '+ $.ua.device.model + ' ('+ $.ua.device.type + ')';
            var os = $.ua.os.name + ' (' + $.ua.os.version + ')';

            if(navigator.geolocation) {
                navigator.geolocation.getCurrentPosition( successCallback, errorCallback, options);
            } else{
              console.log("Your browser does not support HTML5 geolocation.");
              self.get_api_location(selected_id, model, modelName, null, null, '',
               device, os, employee_id, analytic_id);
              }

            function html5_success(data)
            {
                var ip = data['ip'];
                var message = 'CLIENT SHARED POSITION'
                self.create_starting_data(selected_id, model, modelName, ip, lat, long, message,
                device, os, employee_id, analytic_id);
            }
            function html5_fail(err)
            {
                var message = 'HTML5 GEOLOCATION WITHOUT IP'
                self.create_starting_data(selected_id, model, modelName, null, lat, long, message,
                device, os, employee_id, analytic_id);
            }
            // Define callback function for successful attempt
            function successCallback(position){

                lat = position.coords.latitude;
                long =  position.coords.longitude;

                jQuery.ajax({
                dataType: 'json',
                url: 'https://jsonip.com',
                success: html5_success,
                error: html5_fail
                });

                }

            // Define callback function for failed attempt
            function errorCallback(error){
                var message = ''
                if(error.code == 1)
                {
                    message = 'Client refused to share position';
                    console.log("You've decided not to share your position.");
                } else if(error.code == 2){
                    message = 'Network down or positioning service can not be reached';
                    console.log("The network is down or the positioning service can't be reached.");
                } else if(error.code == 3){
                    message= 'The attempt timed out';
                    console.log("The attempt timed out before it could get the location data.");
                } else{
                    message = 'Geolocation failed due to unkown error',
                    console.log("Geolocation failed due to unknown error.");
                }
                self.get_api_location(selected_id, model, modelName, null, null, message,
                device, os, employee_id, analytic_id);
                }
            }

        get_api_location(selected_id, model, modelName, lat, long, message,
        device, os, employee_id, analytic_id)
         {
          var self = this;

          function location_success(data)
          {
               var mess = 'API IPSTACK'
               self.create_starting_data(selected_id, model, modelName,
               data['ip'], data['latitude'], data['longitude'], mess, device, os, employee_id, analytic_id);
          }
          function location_fail(err)
          {
               var mess = 'GEOLOCATION AND API IPSTACK FAILED'
               self.create_starting_data(selected_id, model, modelName,
                null, null, null, mess, device, os, employee_id, analytic_id);
          }
          function ip_success(data)
          {
             var ip = data['ip'];
             jQuery.ajax({
                dataType: 'json',
                url: 'http://api.ipstack.com/'+ip+'?access_key=bab13d9f95bcef77f67e78e4933b6e16',
                success: location_success,
                error: location_fail
             });
          }

          function ip_fail(err) {
            var mess = 'GETTING CLIENT IP FAILED'
            self.create_starting_data(selected_id, model, modelName, null, null, null, mess, device, os,employee_id, analytic_id);
          }

          jQuery.ajax({
                dataType: 'json',
                url: 'https://jsonip.com',
                success: ip_success,
                error: ip_fail
          });
        }

        create_starting_data(selected_id, model, modelName, ip, lat, long,
        message, device, os, employee_id, analytic_id){
            var self = this;
            var checked_ids = this.getSelectedItems('check-to-move');
                var selected_id = $(model.currentTarget).data('value');
                if (!checked_ids) {
                    checked_ids = [selected_id];
                }
                else{
                    if(!checked_ids.includes(selected_id)){checked_ids.push(selected_id);}
                }
            var args = { 'ip': ip,
                         'latitude': lat,
                         'longitude': long,
                         'geolocation_message': message,
                         'device': device,
                         'os': os,
                         'employee_id': employee_id,
                         'analytic_id': analytic_id}
            self.move_to_stage(selected_id, checked_ids, modelName, 'ToDo', 'Working', args);


        }
        
//      NEW METHODS THAT ALLOWS WORKORDER TRACKING!
//      ToDo. merge step tracking and workorder using the same methods
        move_to_stage(selected_id, checked_ids, modelName, from_stage, to_stage, args_extra){
            var self = this;
            console.log('MOVING TO STAGE ...');
           if(to_stage == 'Finished')
           {
            Dialog.confirm(this, "Are you sure you want to finish this activity? This action can't be undone.",
            {
            confirm_callback: function () {
                rpc.query({
                model: 'time.tracking.actions',
                method: 'move_to_stage',
                args: [{}, checked_ids, modelName, from_stage, to_stage, args_extra]
                }).then((result) => {
                    if(result){
                         rpc.query({
                             model: 'time.tracking.actions',
                             method: result[0],
                             args: [{}, result[1], result[2], result[3]],
                            }).then((action) => {
                            if (action){
                                web_client.do_action(action, {
                                on_close: () => {
                                    self._controller.reload();
                                },
                              })
                            }else{
                                self._controller.reload();
                            }
                        });
                    }
                    self._controller.reload();});
            },
        });
           }else{
           rpc.query({
                model: 'time.tracking.actions',
                method: 'move_to_stage',
                args: [{}, checked_ids, modelName, from_stage, to_stage, args_extra]
                }).then((result) => {
                    if(result){
                         rpc.query({
                             model: 'time.tracking.actions',
                             method: result[0],
                             args: [{}, result[1], result[2], result[3]],
                            }).then((action) => {
                            if (action){
                                web_client.do_action(action, {
                                on_close: () => {
                                    self._controller.reload();
                                },
                                })
                            }else{
                                self._controller.reload();
                            }
                        });
                    }
                    self._controller.reload();});
           }

//        END OF NEW METHODS
}

    select_check(option, action, ev) {
        var checks = $('input:checkbox[id^="check-to-' + option + '-"]');
        for(var i=0; i< checks.length; i++){checks[i].checked = action;}
    }

    select_show(option, ev) {
        var div = $('div[id^="dataContainer-' + option + '"]');
        var button = $('i[id^="tracking-show-' + option + '"]');
        for(var i=0; i< div.length; i++){

            if (button[0].className === 'fa fa-angle-up') {
                $("#"+ button[0].id).removeClass("fa-angle-up").addClass("fa-angle-down");
                $("#"+ div[0].id).slideUp();
            }
            else if (button[0].className === 'fa fa-angle-down') {
                $("#"+ button[0].id).removeClass("fa-angle-down").addClass("fa-angle-up");
                $("#"+ div[0].id).slideDown();
            }
        }
    }
    select_active(option, ev) {
        var button = $('i[id^="tracking-active-' + option + '"]');
        if (button[0].className === 'fa fa-check-square') {
                $("#"+ button[0].id).removeClass("fa-check-square").addClass("fa-square");
        }else if (button[0].className === 'fa fa-square') {
                $("#"+ button[0].id).removeClass("fa-square").addClass("fa-check-square");
            }
        this.select_check(option, true, null);
        var checks = {'op0': 'analytic_check',
                      'op3': 'wo_check',
                      'op5': 'workcenter_check',
                      'op6': 'department_check',
                      'op7': 'periodg_check',
                      'op8': 'period_check',
                      'op9': 'period_day_check'}
        this.stepFilter(checks[option], ev);
    }

    stepFilter(click_origin, ev) {
            ev.preventDefault();
            var $action = $(ev.currentTarget);
            var filter_workcenter_ids = this._renderer.state.context['filter_workcenter_ids'];
            var origin = this._renderer.state.context['origin'];
            var filters = this._renderer.state.context['filters'];
            var indexes = {'periodg': 0, 'period': 1, 'period_day':2, 'department':3, 'workcenter':4,
                            'analytic':5, 'wo':6};
            var active_filter = this.checkActive(origin[1]);
            var period_day = false
//            Replace arguments depending of origin ...
            switch(click_origin){
                case 'periodg_check':
                    filters[indexes['periodg']] = this.getSelectedItems('check-to-op7', 'all');
//                    filters.length = indexes['periodg'] + 1;
                    break;
                case 'periodg_link':
                    filters[indexes['periodg']] = [$action.data('period_group_id')];
//                    filters.length = indexes['periodg'] + 1;
                    break;
                case 'period_check':
                    filters[indexes['period']] = this.getSelectedItems('check-to-op8', 'all');
                    period_day = true
//                    filters.length = indexes['period'] + 1;
                    break;
                case 'period_link':
                    filters[indexes['period']] = [$action.data('period_id')];
                    period_day = true
//                    filters.length = indexes['period'] + 1;
                    break;
                case 'department_check':
                    filters[indexes['department']] = this.getSelectedItems('check-to-op6', 'all');
//                    filters.length = indexes['department'] + 1;
                    break;
                case 'department_link':
                    filters[indexes['department']] = [$action.data('department_id')];
//                    filters.length = indexes['department'] + 1;
                    break;
                case 'workcenter_link':
                    filters[indexes['workcenter']] = [$action.data('workcenter_id')];
//                    filters.length = indexes['workcenter'] + 1;
                    break;
                case 'workcenter_check':
                    filters[indexes['workcenter']] = this.getSelectedItems('check-to-op5', 'all');
//                    filters.length = indexes['workcenter'] + 1;
                    break;
                case 'analytic_check':
                    filters[indexes['analytic']] = this.getSelectedItems('check-to-op0', 'all');
//                    filters.length = indexes['analytic'] + 1;
                    break;
                case 'analytic_link':
                    filters[indexes['analytic']] = [$action.data('analytic_id')];
//                    filters.length = indexes['analytic'] + 1;
                    break;
                case 'wo_check':
                    filters[indexes['wo']] = this.getSelectedItems('check-to-op3', 'all');
//                    filters.length = indexes['wo'] + 1;  //check filter.xml
                    break;
                case 'wo_link':
                    filters[indexes['wo']] = [$action.data('workorder_id')];
//                    filters.length = indexes['wo'] + 1;
                    break;
                case 'period_day_check':
                    filters[indexes['period_day']] = this.getSelectedItems('check-to-op9', 'all');
//                    filters.length = indexes['period_day'] + 1;  //check filter.xml
                    break;
                case 'period_day_link':
                    filters[indexes['period_day']] = [$action.data('period_day_id')];
//                    filters.length = indexes['period_day'] + 1;
                    break;
            }

            this.loadSteps([{}, filter_workcenter_ids,  origin, filters, active_filter,
                            this.checkDisplay(origin[1]), period_day]);
    }
    checkActive(origin){
        var options_keys = ['op7', 'op8', 'op9', 'op6', 'op5', 'op0', 'op3'];
        var active = []
        for(var i = 0; i < options_keys.length; i++)
        {
            active.push(this.validateStatus(options_keys[i], 'active', 'fa fa-check-square'));
        }
        return active;
    }
    checkDisplay(origin){
        var options_keys = ['op7', 'op8', 'op9', 'op6', 'op5', 'op0', 'op3'];
        var active = []
        for(var i = 0; i < options_keys.length; i++)
        {
            active.push(this.validateStatus(options_keys[i], 'show', 'fa fa-angle-up'));
        }
        return active;
    }
    validateStatus(option, status, element_class){
        var button = $('i[id^="tracking-' + status + '-' + option + '"]');
        var active = false;
        if (button[0].className === element_class) {
            active = true;
        }
        return active;
    }
    loadSteps(args)
    {
        var self = this;
        rpc.query({
                model: 'mrp.timetracking',
                method: 'get_tracking_filter',
                args: args

            }).then(function(result){
                var model = 'mrp.timetracking';
                var is_supervisor = false;
                if(args[1].length > 1)
                {
                    is_supervisor = true;
                }
                web_client.do_action({
                name: 'tracking by ' + args[2][0],
                res_model: model,
                views: [[result[0][0] || false, 'kanban'], [result[0][1] || false, 'gantt']],
                type: 'ir.actions.act_window',
                domain:[
                        ['id', 'in', result[4]]
                    ],
                context:{
                        filter_workcenter_ids: result[1],
                        origin: result[2],
                        filters: result[3],
                        period_group_ids: result[5],
                        period_ids: result[6],
                        department_ids: result[7],
                        workcenter_ids: result[8],
                        analytic_ids: result[9],
                        party_ids: result[10],
                        workorder_ids: result[11],
                        period_day_ids: result[12],
                        filters_active: result[13],
                        filters_display: result[14],
                        is_supervisor: is_supervisor}
                },
                 {
                    on_reverse_breadcrumb: self.on_reverse_breadcrumb,
                    clear_breadcrumbs: true
                    });
                });
    }
    getItemIds(items) {
            var ids = [];
            items.each((idx, item) => {
                var id = $(item).attr('id').split('-').pop();
                var parse_id = parseInt(id);
                ids.push(parse_id);
            });
            return ids;
        }

        getSelectedItems(selector, default_value=null) {
            var items = $('input:checked[id^="'+ selector +'"]');
            if (items.length)
                return this.getItemIds(items);
            if(default_value == 'all'){
                var items = $('input[id^="'+ selector +'"]');
                if (items.length)
                    return this.getItemIds(items);
            }
            return false;
        }
}

    return TimetrackingActions;
});
