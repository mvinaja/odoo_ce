odoo.define('aci_estimation.KanbanColumnWorkflow', function (require) {
    'use strict';

    var KanbanColumn = require('web.KanbanColumn');
    var core = require('web.core');
    var config = require('web.config');

    var KanbanColumnProgressBar = require('web.KanbanColumnProgressBar');
    var QWeb = core.qweb;
    var _t = core._t;
    var _lt = core._lt;

    KanbanColumn.include({
        init: function (parent, data, options, recordOptions) {
            this._super(parent, data, options, recordOptions);

            // ACI Code: Init custom members
            this.parent_renderer = parent.__parentedParent.renderer;
            this.view_attrs = parent.__parentedParent.renderer.arch.attrs;
            this.is_draggable_columns = this.view_attrs.is_draggable_columns;
        },

        start: function () {
            var self = this;
            // var defs = [this._super.apply(this, arguments)];
            this.$header = this.$('.o_kanban_header');
            for (var i = 0; i < this.data_records.length; i++) {
                this._addRecord(this.data_records[i]);
            }
            this.$header.find('.o_kanban_header_title').tooltip();

            // ACI Code: Initialize selector to disabled cards;
            //           Activate drag and drop to mobile devices
            var disabled_cards = '', dnd_mobile_device = false;
            if (this.is_draggable_columns) {
                this.draggable = false,
//                console.log(this.draggable,"draggable")
//                disabled_cards = 'div.oe_kanban_card[isdisabled="true"]';
//                disabled_cards_checkbox = 'div.oe_kanban_card[isdisabled="true"]';
                dnd_mobile_device = true;
            }

            // ACI Code: Change condition for activate drag and drop on mobile devices
            // if (!config.device.isMobile && this.draggable !== false) {
//            console.log(config,"Is mobile")
            if (this.draggable !== false && (!config.device.isMobile || dnd_mobile_device)) {
                // deactivate sortable in mobile mode.  It does not work anyway,
                // and it breaks horizontal scrolling in kanban views.  Someday, we
                // should find a way to use the touch events to make sortable work.
                this.$el.sortable({
                    connectWith: '.o_kanban_record',
                    revert: 0,
                    delay: 0,
                    items: '> .o_kanban_record:not(.o_updating)',
                    helper: 'clone',
                    cursor: 'move',
                    // ACI Code: Disabled cards
//                    containment: 'parent',
//                    cancel: 'div.oe_kanban_card_draggable',
//                    cancel: disabled_cards,
                    over: function () {
                        self.$el.addClass('o_kanban_hover');
                    },
                    out: function () {
                        self.$el.removeClass('o_kanban_hover');
                    },
                    update: function (event, ui) {
                        var record = ui.item.data('record');
                        var index = self.records.indexOf(record);
                        record.$el.removeAttr('style');  // jqueryui sortable add display:block inline

                        // ACI Code: Handle change of stage
                        if (self.is_workflow_columns)
                            if (event.type === 'sortupdate') {
                                var stage = $(event.target).attr('data-id');
                                if (!self.parent_renderer.timetrackingObject.getOriginStage()) {
                                    self.parent_renderer.timetrackingObject.setOriginStage(stage);
                                    self.parent_renderer.timetrackingObject.setRecord(record);
                                } else
                                    self.parent_renderer.timetrackingObject.setTargetStage(stage);
                            }

                        if (index >= 0) {
                            if ($.contains(self.$el[0], record.$el[0])) {
                                // resequencing records
                                self.trigger_up('kanban_column_resequence', {ids: self._getIDs()});
                            }
                        } else {
                            // adding record to this column
                            ui.item.addClass('o_updating');
                            self.trigger_up('kanban_column_add_record', {record: record, ids: self._getIDs()});
                        }
                    }
                });
            }
            this.$el.click(function (event) {
                if (self.folded) {
                    self._onToggleFold(event);
                }
            });
            if (this.barOptions) {
                this.$el.addClass('o_kanban_has_progressbar');
                this.progressBar = new KanbanColumnProgressBar(this, this.barOptions, this.data);
                // defs.push(this.progressBar.appendTo(this.$header));
            }

            var title = this.folded ? this.title + ' (' + this.data.count + ')' : this.title;

//            if(title == 'Working'){
//                this.column = $('div.o_kanban_group:nth-child(1)').css("background-color", 'red')
//                console.log(this.column,"Column")
//                this.$header.find('.o_kanban_no_records').css("background-color", 'red')
//                $('.o_kanban_no_records').css("background-color", 'red')
//            }
           if(title == 'Working' && this.is_draggable_columns){
//                this.column = $('div.o_kanban_group:nth-child(1)').css("background-color", 'red');
                this.$header.find('.o_kanban_header_title').html("<div><i class='button_tittle_kanban fa fa-step-little'></i>&nbsp;<label class='button_tittle_text_kanban'>"+ title +"</label></div>");
//                this.$header.find('.o_kanban_header_title').css("background-color", 'red')
//                $('.o_kanban_no_records').css("background-color", 'red')
            }
           if(title == 'Blocked' && this.is_draggable_columns){
                this.$header.find('.o_kanban_header_title').html("<div><i class='button_tittle_kanban fa fa-locked'></i><label class='button_tittle_text_kanban'>"+ title +"</label></div>");
            }
            if(title == 'Finished' && this.is_draggable_columns){
                this.$header.find('.o_kanban_header_title').html("<div><i class='button_tittle_kanban fa fa-finished-track'></i>&nbsp;<label class='button_tittle_text_kanban'>&nbsp;"+ title +"</label></div>");
            }
            if(title == 'Cancel' && this.is_draggable_columns){
                this.$header.find('.o_kanban_header_title').html("<div><i class='button_tittle_kanban fa fa-cancel-circle'></i><label class='button_tittle_text_kanban'>"+ title +"</label></div>");
            }
            if(title == 'ToDo' && this.is_draggable_columns){
                this.$header.find('.o_kanban_header_title').html("<div><i class='button_tittle_kanban fa fa-pause-circles'></i><label class='button_tittle_text_kanban'>"+ title +"</label></div>");
            }
            this.$header.find('.o_column_title').text(title);

            this.$el.toggleClass('o_column_folded', this.folded && !config.device.isMobile);
            var tooltip = this.data.count + _t(' records');
            tooltip = '<p>' + tooltip + '</p>' + this.tooltipInfo;
            this.$header.find('.o_kanban_header_title').tooltip({html: true}).attr('data-original-title', tooltip);
            if (!this.remaining) {
                this.$('.o_kanban_load_more').remove();
            } else {
                this.$('.o_kanban_load_more').html(QWeb.render('KanbanView.LoadMore', {widget: this}));
            }

            if(['category_filter'].includes(this.view_attrs['default_group_by']))
            {
              this.$header.find('.o_kanban_header_title').css("background-color", '#ffe7ad');
              this.$header.find('.o_kanban_header_title').css("height", '20px');
              this.$el.css("width", '100%');
              this.parent_renderer.$el.css("display", 'grid');
            }
//.o_kanban_view .o_kanban_group:not(.o_column_folded)
            // return $.when.apply($, defs);
        },
    });
});
