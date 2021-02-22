odoo.define('aci_estimation.KanbanControllerActivities', function (require) {
    'use strict';

    var core = require('web.core');
    var KanbanController = require('web.KanbanController');

    var qweb = core.qweb;

    var TimetrackingActions = require('aci_estimation.TimeTrackWorkflow');
    var framework = require('web.framework');
    var rpc = require('web.rpc');


    KanbanController.include({
        init: function (parent, model, renderer, params) {

            this._super(parent, model, renderer, params);

            if(renderer.state.context['filter_workcenter_ids'] != null){
                this.workorder_ids = renderer.state.context['workorder_ids'];
                this.is_supervisor =  renderer.state.context['is_supervisor'];
                this.party_ids =  renderer.state.context['party_ids'];
                this.filter_workcenter_ids = renderer.state.context['filter_workcenter_ids'];
                this.workcenter_ids = renderer.state.context['workcenter_ids'];
                this.analytic_ids = renderer.state.context['analytic_ids'];
                this.department_ids = renderer.state.context['department_ids'];
                this.origin = renderer.state.context['origin'];
                this.period_group_ids = renderer.state.context['period_group_ids'];
                this.period_ids = renderer.state.context['period_ids'];
                this.period_day_ids = renderer.state.context['period_day_ids'];
                this.filters = renderer.state.context['filters'];
                this.filters_active = renderer.state.context['filters_active'];
                this.filters_display = renderer.state.context['filters_display'];
            }
            else{
                this.workorder_ids = [];
                this.is_supervisor =  false;
                this.party_ids =  [];
                this.filter_workcenter_ids = [];
                this.workcenter_ids = [];
                this.analytic_ids = [];
                this.department_ids = [];
                this.origin = [];
                this.period_group_ids = [];
                this.period_ids = [];
                this.period_day_ids = [];
                this.filters = [];
                this.filters_active = [];
                this.filters_display = [];
            }
            if(renderer.state.context['category'] != null)
            { this.category=true;}
            else{this.category=null}
            // ACI Code:
            this.is_workflow_columns = this.renderer.arch.attrs.workflow_columns
            if (this.is_workflow_columns) {
                this.renderer.timetrackingObject = new TimetrackingActions(this.modelName, this.renderer, this);
            }
        },
         events: _.extend({}, KanbanController.prototype.events, {
            'click .o_kanban_time_tracking_button_working': 'working_button_step_kanban',
            'click .o_kanban_time_tracking_button_todo': 'todo_button_step_kanban',
            'click .o_kanban_time_tracking_button_blocked': 'blocked_button_step_kanban',
            'click .o_kanban_time_tracking_button_finished': 'finished_button_step_kanban',
            'click .o_kanban_time_tracking_button_cancel': 'cancel_button_step_kanban',

        }),

        _loadTemplate() {
            var $buttonns = $(qweb.render('kanban-box'));
        },

        willStart: function () {
            var self = this;
            return $.when(this._super.apply(this, arguments));
        },

        renderButtons: function ($node) {
            this._super.apply(this, arguments);
            this.addTimeTrackingButtons($node);
        },

        addTimeTrackingButtons: function ($node) {
            if (this.is_workflow_columns) {
                var $buttons = $(qweb.render('KanbanTimeTracking.buttons', {widget: this})),
                timeTrackingObject = this.renderer.timetrackingObject;

                $buttons.on('click', '.department_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'department_link'));
                $buttons.on('click', '.department_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'department_check'));
                $buttons.on('click', '.workcenter_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'workcenter_link'));
                $buttons.on('click', '.workcenter_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'workcenter_check'));
                $buttons.on('click', '.production_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'production_link'));
                $buttons.on('click', '.production_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'production_check'));
               $buttons.on('click', '.wo_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'wo_link'));
                $buttons.on('click', '.wo_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'wo_check'));
                $buttons.on('click', '.party_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'party_link'));
                $buttons.on('click', '.party_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'party_check'));
                $buttons.on('click', '.analytic_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'analytic_link'));
                $buttons.on('click', '.analytic_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'analytic_check'));
                $buttons.on('click', '.periodg_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'periodg_link'));
                $buttons.on('click', '.periodg_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'periodg_check'));
                $buttons.on('click', '.period_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'period_link'));
                $buttons.on('click', '.period_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'period_check'));
                $buttons.on('click', '.period_day_link',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'period_day_link'));
                $buttons.on('click', '.period_day_check',
                    timeTrackingObject.stepFilter.bind(timeTrackingObject, 'period_day_check'));

                $buttons.on('click', 'button.o_kanban_time_tracking_button_op0_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op0'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op1_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op1'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op2_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op2'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op3_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op3'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op4_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op4'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op5_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op5'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op6_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op6'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op7_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op7'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op8_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op8'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op9_show',
                    timeTrackingObject.select_show.bind(timeTrackingObject, 'op9'));

                $buttons.on('click', 'button.o_kanban_time_tracking_button_op0_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op0'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op1_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op1'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op2_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op2'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op3_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op3'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op4_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op4'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op5_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op5'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op6_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op6'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op7_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op7'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op8_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op8'));
                $buttons.on('click', 'button.o_kanban_time_tracking_button_op9_active',
                    timeTrackingObject.select_active.bind(timeTrackingObject, 'op9'));

                if ($node) {
                            $buttons.appendTo($node);
                        } else {
                            this.$('div.o_cp_bottom_left').replaceWith($buttons);
                        }
        }},

        working_button_step_kanban: function (model) {
            model.preventDefault();
            var self = this;
            var $action = $(model.currentTarget);
            self.renderer.timetrackingObject.getGeoLocation(model);
            },

        todo_button_step_kanban: function (model) {

            this.renderer.timetrackingObject._loadStageLabels(model,'todo');

        },

        blocked_button_step_kanban: function (model) {

             this.renderer.timetrackingObject._loadStageLabels(model,'blocked');

        },

        finished_button_step_kanban: function (model) {

              this.renderer.timetrackingObject._loadStageLabels(model,'finished');

        },

        cancel_button_step_kanban: function (model) {

               this.renderer.timetrackingObject._loadStageLabels(model,'cancel');

        },

        _do_check_out (render){
            var self = this;
            var models = 'lbm.work.order.step';
            self._rpc({
                model: models,
                method: 'do_check_out'
                });
        },
    });
});
