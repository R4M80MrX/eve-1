#Embedded file name: c:/depot/games/branches/release/EVE-TRANQUILITY/eve/client/script/ui/shared/neocom/help.py
import blue
import service
import util
import urllib
import listentry
import uicls
import uiconst
import localization

class HelpWindow(uicls.Window):
    __guid__ = 'form.HelpWindow'
    __notifyevents__ = ['ProcessSessionChange']
    default_width = 300
    default_height = 458
    default_windowID = 'help'

    def ApplyAttributes(self, attributes):
        uicls.Window.ApplyAttributes(self, attributes)
        self.SetScope('station_inflight')
        self.SetCaption(localization.GetByLabel('UI/Help/EveHelp'))
        self.SetWndIcon('74_14')
        self.SetMinSize([300, 458], 1)
        self.LockWidth(300)
        self.SetTopparentHeight(64)
        self.MakeUnpinable()
        self.MouseDown = self.OnWndMouseDown
        self.supportLoaded = False
        self.tutorialsLoaded = False
        supportPar = uicls.Container(name='supportPar', parent=self.sr.main, left=const.defaultPadding, top=const.defaultPadding, width=const.defaultPadding, height=const.defaultPadding)
        tutorialsPar = uicls.Container(name='tutorialPar', parent=self.sr.main, pos=(0, 0, 0, 0))
        t = [[localization.GetByLabel('UI/Help/Support'),
          supportPar,
          self,
          ('support',)], [localization.GetByLabel('UI/Help/Tutorials'),
          tutorialsPar,
          self,
          ('tutorials',)]]
        tabs = uicls.TabGroup(name='tabparent', parent=self.sr.main, idx=0, tabs=t, autoselecttab=0)
        tabs.ShowPanelByName(attributes.showPanel or localization.GetByLabel('UI/Help/Support'))
        self.sr.mainTabs = tabs
        uicls.CaptionLabel(text=localization.GetByLabel('UI/Help/EveHelp'), parent=self.sr.topParent, align=uiconst.CENTERLEFT, left=70)

    def ProcessSessionChange(self, isremote, session, change):
        if session.charid is None:
            self.Close()

    def LoadTabPanel(self, args, panel, tabgroup):
        if args:
            key = args[0]
            if key == 'tutorials':
                self.LoadTutorials(panel)
            elif key == 'support':
                self.LoadSupport(panel)

    def LoadTutorials(self, panel, *args):
        if self.tutorialsLoaded:
            return
        scroll = uicls.Scroll(parent=panel, left=const.defaultPadding, top=const.defaultPadding, width=const.defaultPadding, height=const.defaultPadding)
        scroll.multiSelect = 0
        scroll.OnSelectionChange = self.OnScrollSelectionChange
        scroll.Confirm = self.OpenSelectedTutorial
        byCategs = sm.GetService('tutorial').GetTutorialsByCategory()
        categsNames = []
        for categoryID in byCategs.keys():
            if categoryID is not None:
                categoryInfo = sm.GetService('tutorial').GetCategory(categoryID)
                categoryName = localization.GetByMessageID(categoryInfo.categoryNameID)
                categoryDesc = localization.GetByMessageID(categoryInfo.descriptionID)
                categsNames.append((categoryName, (categoryID, categoryDesc)))
            else:
                categsNames.append(('-- No category Set! --', (categoryID, '')))

        categsNames.sort()
        scrolllist = []
        for label, (categoryID, hint) in categsNames:
            if categoryID is None and not eve.session.role & (service.ROLE_GML | service.ROLE_WORLDMOD):
                continue
            data = {'GetSubContent': self.GetTutorialGroup,
             'label': label,
             'id': ('tutorial', categoryID),
             'groupItems': byCategs[categoryID],
             'showicon': 'hide',
             'BlockOpenWindow': 1,
             'state': 'locked',
             'showlen': 0,
             'hint': hint}
            scrolllist.append(listentry.Get('Group', data))

        scroll.Load(contentList=scrolllist)
        buttonList = [[localization.GetByLabel('UI/Help/OpenTutorial'), self.OpenSelectedTutorial, ()], [localization.GetByLabel('UI/Help/ShowCareerAgents'), self.ShowTutorialAgents, ()]]
        if session.role & service.ROLE_CONTENT:
            buttonList.append(['Clear Cache', self.CloseTutorialService, ()])
        btns = uicls.ButtonGroup(btns=buttonList, line=1, unisize=0)
        panel.children.insert(0, btns)
        tutorialBtn = btns.sr.Get(localization.GetByLabel('UI/Help/ShowCareerAgents') + 'Btn')
        if tutorialBtn:
            tutorialBtn.hint = localization.GetByLabel('UI/Help/CareerAgentsExplanation')
        self.sr.tutorialBtns = btns
        self.sr.tutorialScroll = scroll
        self.tutorialsLoaded = True

    def CloseTutorialService(self):
        sm.StopService('tutorial')
        self.CloseByUser()

    def GetTutorialGroup(self, nodedata, newitems = 0):
        if not len(nodedata.groupItems):
            return []
        scrolllist = []
        for tutorialData in nodedata.groupItems:
            label = localization.GetByMessageID(tutorialData.tutorialNameID)
            data = {'label': label,
             'sublevel': 1,
             'OnDblClick': self.OpenTutorial,
             'tutorialData': tutorialData,
             'tutorialID': tutorialData.tutorialID}
            if tutorialData.otherRace:
                data['fontColor'] = (1, 1, 1, 0.5)
            entry = listentry.Get('TutorialEntry', data)
            scrolllist.append(entry)

        return scrolllist

    def OnScrollSelectionChange(self, selected, *args):
        openBtn = self.sr.tutorialBtns.sr.Get(localization.GetByLabel('UI/Help/EveHelp') + 'Btn')
        if openBtn:
            if selected:
                openBtn.state = uiconst.UI_NORMAL
            else:
                openBtn.state = uiconst.UI_HIDDEN

    def ShowTutorialAgents(self, *args):
        if util.IsWormholeSystem(eve.session.solarsystemid) or eve.session.solarsystemid == const.solarSystemPolaris:
            raise UserError('NoAgentsInWormholes')
        sm.StartService('tutorial').ShowCareerFunnel()

    def CreateBugReport(self, *args):
        self.Close()
        blue.pyos.synchro.SleepWallclock(10)
        sm.GetService('bugReporting').StartCreateBugReport()

    def OpenSelectedTutorial(self, *args):
        sel = self.sr.tutorialScroll.GetSelected()
        if sel:
            tutorialData = getattr(sel[0], 'tutorialData', None)
            if tutorialData is None:
                return
            sm.GetService('tutorial').OpenTutorial(tutorialData.tutorialID)
        else:
            info = localization.GetByLabel('UI/Help/MustSelectSomething')
            raise UserError('CustomInfo', {'info': info})

    def OpenTutorial(self, entry):
        tutorialData = entry.sr.node.tutorialData
        sm.GetService('tutorial').OpenTutorial(tutorialData.tutorialID)

    def LoadSupport(self, panel, *args):
        if self.supportLoaded:
            return
        subpar = uicls.Container(name='subpar', parent=panel, align=uiconst.TOALL)
        helpchannelpar = uicls.Container(name='helpchannelpar', parent=subpar, align=uiconst.TOTOP)
        helpchannelpar.padTop = 4
        helpbtnparent = uicls.Container(name='helpbtnparent', parent=subpar, align=uiconst.TOTOP, height=32)
        helpchannelbtn = uicls.Button(parent=helpbtnparent, label=localization.GetByLabel('UI/Help/JoinChannel'), func=self.JoinHelpChannel, btn_default=0, align=uiconst.TOPRIGHT)
        helpchannelbtn.left = 6
        helptext = uicls.EveLabelMedium(name='label', text=localization.GetByLabel('UI/Help/JoinChannelHint'), parent=helpchannelpar, align=uiconst.TOPLEFT, pos=(8, 4, 280, 0), state=uiconst.UI_NORMAL)
        helpchannelpar.height = helptext.textheight
        helpbtnparent.height = helpchannelbtn.height + 4
        uicls.Line(parent=subpar, align=uiconst.TOTOP)
        petpar = uicls.Container(name='petitionpar', parent=subpar, align=uiconst.TOTOP, height=60)
        petpar.padTop = 4
        petbtnparent = uicls.Container(name='petbtnparent', parent=subpar, align=uiconst.TOTOP, height=32)
        petbtn = uicls.Button(parent=petbtnparent, label=localization.GetByLabel('UI/Help/FilePetition'), func=self.FilePetition, btn_default=0, align=uiconst.TOPRIGHT)
        petbtn.left = 6
        pettext = uicls.EveLabelMedium(name='label', text=localization.GetByLabel('UI/Help/OpenPetitions'), parent=petpar, align=uiconst.TOPLEFT, pos=(8, 4, 280, 0), state=uiconst.UI_NORMAL)
        petpar.height = pettext.textheight
        petbtnparent.height = petbtn.height + 4
        uicls.Line(parent=subpar, align=uiconst.TOTOP)
        kbpar = uicls.Container(name='kbpar', parent=subpar, align=uiconst.TOTOP, height=60)
        kbpar.padTop = 4
        kbbtnparent = uicls.Container(name='kbbtnparent', parent=subpar, align=uiconst.TOTOP, width=96)
        kbt = localization.GetByLabel('UI/Help/EvelopediaHintText')
        kbtext = uicls.EveLabelMedium(name='label', text=kbt, parent=kbpar, align=uiconst.TOPLEFT, pos=(8, 4, 280, 0), state=uiconst.UI_NORMAL)
        kbbtn = uicls.Button(parent=kbbtnparent, label=localization.GetByLabel('UI/Help/SearchEvelopedia'), func=self.SearchKB, pos=(6, 0, 0, 0), align=uiconst.TOPRIGHT, btn_default=1)
        self.sr.kbsearch = uicls.SinglelineEdit(name='kbsearch', parent=kbbtnparent, pos=(kbbtn.width + 14,
         0,
         195,
         0), align=uiconst.TOPRIGHT)
        kbpar.height = kbtext.textheight
        kbbtnparent.height = max(kbbtn.height, self.sr.kbsearch.height) + 8
        uicls.Line(parent=subpar, align=uiconst.TOTOP)
        funnelpar = uicls.Container(name='funnelpar', parent=subpar, align=uiconst.TOTOP, height=60)
        funnelpar.padTop = 4
        funnelbtnparent = uicls.Container(name='funnelbtnparent', parent=subpar, align=uiconst.TOTOP, width=96, height=32)
        funnelbt = localization.GetByLabel('UI/Help/CareerAdvancementFull')
        funneltext = uicls.EveLabelMedium(name='label', text=funnelbt, parent=funnelpar, align=uiconst.TOPLEFT, pos=(8, 4, 280, 0), state=uiconst.UI_NORMAL)
        uicls.Button(parent=funnelbtnparent, label=localization.GetByLabel('UI/Help/ShowCareerAgents'), func=self.ShowTutorialAgents, pos=(6, 0, 0, 0), align=uiconst.TOPRIGHT)
        helpchannelpar.height = helptext.textheight + helptext.top * 2 + 6
        petpar.height = pettext.textheight + pettext.top * 2 + 6
        kbpar.height = kbtext.textheight + kbtext.top * 2 + 6
        funnelpar.height = funneltext.textheight + funneltext.top * 2 + 6
        if int(sm.GetService('machoNet').GetGlobalConfig().get('bugReporting_ShowButton', 0)) > 0:
            uicls.Line(parent=subpar, align=uiconst.TOTOP)
            bugreportpar = uicls.Container(name='bugreportpar', parent=subpar, align=uiconst.TOTOP, height=60)
            bugreportpar.padTop = 4
            bugreportbtnparent = uicls.Container(name='bugreportbtnparent', parent=subpar, align=uiconst.TOTOP, width=96, height=32)
            bugreportbt = localization.GetByLabel('UI/Help/ReportBugFull')
            bugreporttext = uicls.EveLabelMedium(name='label', text=bugreportbt, parent=bugreportpar, align=uiconst.TOPLEFT, pos=(8, 4, 280, 0), state=uiconst.UI_NORMAL)
            uicls.Button(parent=bugreportbtnparent, label=localization.GetByLabel('UI/Help/ReportBug'), func=self.CreateBugReport, pos=(6, -2, 0, 0), align=uiconst.TOPRIGHT)
            helpchannelpar.height = helptext.textheight + helptext.top * 2 + 6
            petpar.height = pettext.textheight + pettext.top * 2 + 6
            kbpar.height = kbtext.textheight + kbtext.top * 2 + 6
            bugreportpar.height = bugreporttext.textheight + bugreporttext.top * 2 + 6
        totalHeight = 0
        for container in subpar.children:
            if container.align == uiconst.TOTOP:
                totalHeight += container.height

        need = self.sr.topParent.height + self.sr.headerParent.height + totalHeight + 40
        self.SetMinSize([self.minsize[0], need])
        uicls.Fill(parent=panel, color=(1.0, 1.0, 1.0, 0.1))
        uicls.Frame(parent=panel, state=uiconst.UI_PICKCHILDREN)
        uicore.registry.SetFocus(self.sr.kbsearch)
        self.supportLoaded = True

    def SearchKB(self, *args):
        search = self.sr.kbsearch.GetValue()
        if search:
            url = 'http://wiki.eveonline.com/en/wiki/Special:Search'
            data = [('search', search), ('go', 'Go')]
            uicore.cmd.OpenBrowser('%s?%s' % (url, urllib.urlencode(data)))

    def Confirm(self, *args):
        if uicore.registry.GetFocus() == self.sr.kbsearch:
            self.SearchKB()

    def FilePetition(self, *args):
        sm.GetService('petition').NewPetition()

    def JoinHelpChannel(self, *etc):
        channels = []
        lsc = sm.StartService('LSC')
        if eve.session.role & service.ROLE_NEWBIE:
            channels.append(lsc.rookieHelpChannel)
        if eve.session.languageID == 'DE':
            channels.append(lsc.helpChannelDE)
        elif eve.session.languageID == 'RU':
            channels.append(lsc.helpChannelRU)
        elif eve.session.languageID == 'JA':
            channels.append(lsc.helpChannelJA)
        else:
            channels.append(lsc.helpChannelEN)
        sm.GetService('LSC').JoinChannels(channels)

    def OnWndMouseDown(self, *args):
        sm.GetService('neocom').BlinkOff('help')

    def _OnClose(self, *args):
        if getattr(self, 'sr', None) and self.sr.Get('form', None):
            self.sr.form.Close()


class TutorialEntry(listentry.Generic):
    __guid__ = 'listentry.TutorialEntry'
    isDragObject = True

    def GetDragData(self, *args):
        nodes = [self.sr.node]
        return nodes