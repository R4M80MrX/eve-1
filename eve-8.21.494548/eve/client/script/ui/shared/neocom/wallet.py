#Embedded file name: c:/depot/games/branches/release/EVE-TRANQUILITY/eve/client/script/ui/shared/neocom/wallet.py
import sys
import blue
import uthread
import uix
import uiutil
import mathUtil
import form
import service
import util
import listentry
import types
import yaml
import uicls
import uiconst
import log
import localization
import localizationUtil

def FmtWalletCurrency(amt, currency = const.creditsISK, showFractions = None):
    if showFractions is None:
        showFractions = settings.user.ui.Get('walletShowCents', 1)
        if not showFractions and abs(amt) > 1:
            amt = int(amt)
    return util.FmtCurrency(amt, showFractionsAlways=showFractions, currency=currency)


from contractutils import DoParseItemType

class NoneNPCAccountOwnerDialog(uicls.Window):
    __guid__ = 'form.NoneNPCAccountOwnerDialog'
    default_width = 320
    default_height = 300
    default_windowID = 'NoneNPCAccountOwnerDialog'

    def ApplyAttributes(self, attributes):
        uicls.Window.ApplyAttributes(self, attributes)
        self.ownerID = None
        self.searchStr = ''
        self.scope = 'all'
        self.Confirm = self.ValidateOK
        self.SetMinSize([320, 300])
        self.SetWndIcon('ui_7_64_6')
        self.sr.errorParent = uicls.Container(name='errorParent', align=uiconst.TOBOTTOM, height=16, parent=self.sr.main, state=uiconst.UI_HIDDEN)
        self.sr.scroll = uicls.Scroll(parent=self.sr.main, padding=(const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding))
        self.sr.scroll.Startup()
        self.sr.scroll.multiSelect = 0
        self.sr.standardBtns = uicls.ButtonGroup(btns=[[localization.GetByLabel('UI/Common/Buttons/OK'),
          self.OnOK,
          (),
          81], [localization.GetByLabel('UI/Common/Buttons/Cancel'),
          self.OnCancel,
          (),
          81]])
        self.sr.main.children.insert(0, self.sr.standardBtns)
        self.SetCaption(localization.GetByLabel('UI/Wallet/WalletWindow/SelectCorpOrChar'))
        self.label = uicls.EveLabelSmall(text=localization.GetByLabel('UI/Shared/TypeSearchString'), parent=self.sr.topParent, left=70, top=16, state=uiconst.UI_NORMAL)
        inpt = uicls.SinglelineEdit(name='edit', parent=self.sr.topParent, pos=(70,
         self.label.top + self.label.height + 2,
         86,
         0), align=uiconst.TOPLEFT, maxLength=32)
        inpt.OnReturn = self.Search
        self.sr.inpt = inpt
        btn = uicls.Button(parent=self.sr.topParent, label=localization.GetByLabel('UI/Wallet/WalletWindow/WalletSearch'), pos=(inpt.left + inpt.width + 2,
         inpt.top,
         0,
         0), func=self.Search, btn_default=1)
        self.SetHint(localization.GetByLabel('UI/Common/TypeInSearch'))

    def Search(self, *args):
        scrolllist = []
        self.ShowLoad()
        try:
            self.searchStr = self.GetSearchStr()
            self.SetHint()
            if len(self.searchStr) < 1:
                self.SetHint(localization.GetByLabel('UI/Shared/PleaseTypeSomething'))
                return
            result = sm.RemoteSvc('lookupSvc').LookupNoneNPCAccountOwners(self.searchStr, 0)
            if result is None or not len(result):
                self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/NoCorpCharFound', searchString=self.searchStr))
                return
            cfg.eveowners.Prime([ each.ownerID for each in result ])
            for each in result:
                owner = cfg.eveowners.Get(each.ownerID)
                scrolllist.append(listentry.Get('Item', {'label': owner.name,
                 'typeID': owner.typeID,
                 'itemID': each.ownerID,
                 'confirmOnDblClick': 1,
                 'OnClick': self.CheckSelected,
                 'listvalue': [owner.name, each.ownerID]}))

        finally:
            self.sr.scroll.Load(fixedEntryHeight=18, contentList=scrolllist, noContentHint=localization.GetByLabel('UI/Wallet/WalletWindow/SearchNoResults'))
            self.CheckSelected()
            self.HideLoad()

    def GetSearchStr(self):
        return self.sr.inpt.GetValue().strip()

    def Confirm(self):
        self.OnOK()

    def ValidateOK(self):
        if self.searchStr != self.GetSearchStr():
            self.Search()
            return 0
        if self.ownerID is None:
            return 0
        return 1

    def SetHint(self, hintstr = None):
        if self.sr.scroll:
            self.sr.scroll.ShowHint(hintstr)

    def OnOK(self, *args):
        sel = self.sr.scroll.GetSelected()
        if sel:
            self.ownerID = sel[0].itemID
            self.CloseByUser()

    def OnCancel(self, *args):
        self.ownerID = None
        self.CloseByUser()

    def CheckSelected(self, *args):
        sel = 1
        if len(self.sr.scroll.GetNodes()) > 0:
            sel = self.sr.scroll.GetSelected()
        self.DisplayPickHint(bool(sel))

    def DisplayPickHint(self, off = 1):
        ep = self.sr.errorParent
        ep.state = uiconst.UI_HIDDEN
        uix.Flush(ep)
        if off:
            ep.state = uiconst.UI_HIDDEN
        else:
            text = localization.GetByLabel('UI/Wallet/WalletWindow/SelectCharacterOrCorp')
            t = uicls.EveLabelMedium(text=text, top=-3, parent=ep, width=self.minsize[0] - 32, state=uiconst.UI_DISABLED, color=(1.0, 0.0, 0.0, 1.0), align=uiconst.CENTER)
            ep.state = uiconst.UI_DISABLED
            ep.height = t.height + 8


WALLET_BILLS_SCROLLID = 'wallet_show_bills'
WALLET_DIVISIONS_SCROLLID = 'wallet_show_divisions'
WALLET_JOURNAL_SCROLLID = 'wallet_show_journal'
WALLET_SHARES_SCROLLID = 'wallet_show_shares'
WALLET_TRANSACTIONS_SCROLLID = 'wallet_show_transactions'

class WalletSvc(service.Service):
    __exportedcalls__ = {'Show': [],
     'SelectWalletDivision': [],
     'AskSetWalletDivision': [],
     'GetWealth': [],
     'GetCorpWealth': [],
     'Blink': [],
     'PayBill': [],
     'GetBillTypes': [],
     'UpdateBills': []}
    __guid__ = 'svc.wallet'
    __notifyevents__ = ['ProcessSessionChange',
     'OnBillReceived',
     'OnAccountChange',
     'OnShareChange',
     'OnOwnOrderChanged',
     'OnSessionChanged',
     'DoSessionChanging']
    __persistvars__ = ['wasVisible']
    __servicename__ = 'wallet'
    __displayname__ = 'Wallet Client Service'
    __dependencies__ = ['window']
    __update_on_reload__ = 0

    def Run(self, memStream = None):
        self.LogInfo('Starting Wallet')
        self.Reset()
        self.blockWelcomeOnDivisionChange = False
        self.corpWalletRoles = {1000: const.corpRoleAccountCanTake1,
         1001: const.corpRoleAccountCanTake2,
         1002: const.corpRoleAccountCanTake3,
         1003: const.corpRoleAccountCanTake4,
         1004: const.corpRoleAccountCanTake5,
         1005: const.corpRoleAccountCanTake6,
         1006: const.corpRoleAccountCanTake7}
        self.wealth = sm.RemoteSvc('account').GetCashBalance(0)
        self.aurWealth = sm.RemoteSvc('account').GetCashBalance(accountKey=const.accountingKeyAUR)
        self.corpWealth = None
        self.corpWealthCacheTime = 0
        self.accKeys = sm.RemoteSvc('account').GetKeyMap()
        self.billTypeByBillTypeID = sm.RemoteSvc('billMgr').GetBillTypes().Index('billTypeID')

    def Stop(self, memStream = None):
        wnd = self.GetWnd()
        if wnd is not None and not wnd.destroyed:
            wnd.Close()
        self.Reset()

    def GetBillTypes(self):
        return self.billTypeByBillTypeID

    def ProcessSessionChange(self, isremote, session, change):
        if session.charid is None:
            self.Stop()

    def DoSessionChanging(self, isremote, session, change):
        accountantStatusChanged = False
        corpAccountKeyChanged = change.has_key('corpAccountKey')
        corpChanged = change.has_key('corpid')
        allianceChanged = change.has_key('allianceid')
        if change.has_key('corprole'):
            old, new = change['corprole']
            old = old & (const.corpRoleAccountant | const.corpRoleJuniorAccountant)
            new = new & (const.corpRoleAccountant | const.corpRoleJuniorAccountant)
            if old != new:
                accountantStatusChange = True
        self.wasVisible = False
        if corpChanged or accountantStatusChanged or allianceChanged or corpAccountKeyChanged:
            wnd = self.GetWnd()
            self.wasVisible = wnd is not None and not wnd.destroyed and wnd.state != uiconst.UI_HIDDEN
            self.Stop()

    def OnSessionChanged(self, isremote, session, change):
        if getattr(self, 'wasVisible', False):
            self.Show()

    def OnOwnOrderChanged(self, order, reason, isCorp):
        if settings.user.ui.Get('notifyOrderChange', 1):
            sm.GetService('neocom').Blink('wallet')
            self.Blink(1, localization.GetByLabel('UI/Wallet/WalletWindow/Orders'))

    def UpdateBills(self):
        if self.mywallet:
            self.mywallet.UpdateBills(1)
        if self.corpwallet:
            self.corpwallet.UpdateBills(0)

    def OnBillReceived(self, *args):
        if settings.user.ui.Get('notifyBillChange', 1):
            sm.GetService('neocom').Blink('wallet')
            wnd = self.GetWnd()
            if wnd:
                wnd.Blink()
        if self.mywallet:
            self.mywallet.UpdateBills(1)
        if self.corpwallet:
            self.corpwallet.UpdateBills(0)

    def OnShareChange(self, shareholderID, corporationID, change):
        if settings.user.ui.Get('notifyShareChange', 1):
            sm.GetService('neocom').Blink('wallet')
            wnd = self.GetWnd()
            if wnd:
                wnd.Blink()
        if self.mywallet:
            self.mywallet.OnShareChange(shareholderID, corporationID, change)
        if self.corpwallet:
            self.corpwallet.OnShareChange(shareholderID, corporationID, change)

    def OnAccountChange(self, accountKey, ownerID, balance):
        log.LogInfo('Wallet::OnAccountChange', accountKey, ownerID, balance)
        if balance is not None:
            if accountKey == 'cash' and ownerID == eve.session.charid:
                if settings.user.ui.Get('notifyAccountChange', 1):
                    self.Blink(1)
                self.wealth = balance
                if self.mywallet and not self.mywallet.destroyed:
                    self.mywallet.SetMoney(self.wealth)
            if accountKey == 'AURUM' and ownerID == eve.session.charid:
                if settings.user.ui.Get('notifyAccountChange', 1):
                    self.Blink(1)
                self.aurWealth = balance
                if self.mywallet and not self.mywallet.destroyed:
                    self.mywallet.SetMoney(self.aurWealth, const.creditsAURUM)
            if accountKey in ('cash', 'cash2', 'cash3', 'cash4', 'cash5', 'cash6', 'cash7') and ownerID == eve.session.corpid:
                corpAccountKey = 1000
                for k in self.accKeys:
                    if accountKey == k.keyName:
                        corpAccountKey = k.keyID
                        break

                if settings.user.ui.Get('notifyAccountChange', 1) and self.HaveReadAccessToCorpWalletDivision(corpAccountKey):
                    self.Blink(0)
                if self.corpwallet and not self.corpwallet.destroyed and corpAccountKey == session.corpAccountKey:
                    self.corpwallet.SetMoney(balance)
                    if self.corpwallet is not None and not self.corpwallet.destroyed and self.corpwallet.sr.tabs:
                        mainTabArgs = self.corpwallet.sr.tabs.GetSelectedArgs()
                        if mainTabArgs in ('divisions',):
                            uthread.new(self.corpwallet.ShowDivisions, True)
        if settings.user.ui.Get('notifyAccountChange', 1):
            sm.GetService('neocom').Blink('wallet')
            wnd = self.GetWnd()
            if wnd:
                wnd.Blink()
        sm.ScatterEvent('OnAccountChange_Local', accountKey, ownerID, balance)

    def PayBill(self, bill):
        if bill.debtorID == session.charid:
            sm.RemoteSvc('billMgr').CharPayBill(bill.billID)
            self.mywallet.UpdateBills(mine=True)
        elif bill.debtorID == session.corpid:
            if const.corpRoleAccountant & session.corprole == const.corpRoleAccountant:
                sm.RemoteSvc('billMgr').PayCorporationBill(bill.billID, fromAccountKey=eve.session.corpAccountKey)
                self.corpwallet.UpdateBills(mine=False)
        elif bill.debtorID == session.allianceid:
            if session.allianceid and const.corpRoleAccountant & session.corprole == const.corpRoleAccountant:
                sm.GetService('alliance').PayBill(bill.billID, fromAccountKey=eve.session.corpAccountKey)
                self.corpwallet.UpdateBills(mine=False)

    def TransferMoney(self, fromID, fromAccountKey, toID, toAccountKey):
        if toID is None:
            dlg = form.NoneNPCAccountOwnerDialog.Open()
            dlg.ShowModal()
            if not dlg.ownerID:
                return
            toID = dlg.ownerID
        form.TransferMoneyWnd.CloseIfOpen()
        w = form.TransferMoneyWnd.Open(fromID=fromID, fromAccountKey=fromAccountKey, toID=toID, toAccountKey=toAccountKey)

    def GetAccountName(self, acctID):
        pass

    def SelectWalletDivision(self, *args):
        choices = uiutil.SortListOfTuples([ (acctID, (sm.GetService('corp').GetCorpAccountName(acctID), acctID)) for acctID in self.GetAccessibleWallets() ])
        retval = uix.ListWnd(choices, listtype='generic', caption=localization.GetByLabel('UI/Wallet/WalletWindow/SelectDivision'))
        if retval:
            self.blockWelcomeOnDivisionChange = True
            sm.GetService('corp').SetAccountKey(retval[1])

    def AskSetWalletDivision(self, *args):
        if prefs.GetValue('wallet_askcorpaccount_%s' % eve.session.corpid, 1) and eve.session.corpAccountKey is None and len(sm.GetService('wallet').GetAccessibleWallets()) > 0:
            if getattr(self, 'isSelectingWalletDivision', False):
                return
            self.isSelectingWalletDivision = True
            try:
                if eve.Message('SelectWalletDivision', {}, uiconst.YESNO) == uiconst.ID_YES:
                    self.SelectWalletDivision()
                else:
                    prefs.SetValue('wallet_askcorpaccount_%s' % eve.session.corpid, 0)
            finally:
                self.isSelectingWalletDivision = False

    def GetWealth(self):
        return self.wealth

    def GetAurWealth(self):
        return self.aurWealth

    def GetCorpWealth(self, accountKey):
        return sm.RemoteSvc('account').GetCashBalance(1, accountKey=accountKey)

    def GetCorpWealthCached1Min(self, accountKey):
        if self.corpWealth is None or blue.os.GetTime() - self.corpWealthCacheTime > MIN:
            self.corpWealth = self.GetCorpWealth(accountKey)
            self.corpWealthCacheTime = blue.os.GetTime()
        return self.corpWealth

    def GetWalletHint(self):
        showFractions = settings.user.ui.Get('walletShowCents', 1)
        personalWealth = util.FmtISK(self.GetWealth(), showFractions)
        canAccess = self.HaveReadAccessToCorpWalletDivision(session.corpAccountKey)
        if canAccess:
            corpWealth = util.FmtISK(self.GetCorpWealthCached1Min(session.corpAccountKey), showFractions)
            hint = localization.GetByLabel('UI/Neocom/WalletBtnHintCorp', iskWealth=personalWealth, corpWealth=corpWealth)
        else:
            hint = localization.GetByLabel('UI/Neocom/WalletBtnHintPersonal', iskWealth=personalWealth)
        return hint

    def Reset(self):
        self.corpwallet = None
        self.mywallet = None
        self.maintabs = None

    def Show(self):
        wnd = self.GetWnd(1)
        if wnd is not None and not wnd.destroyed:
            wnd.Maximize()

    def AmAccountant(self):
        return bool(eve.session.corprole & const.corpRoleAccountant)

    def AmAccountantOrJuniorAccountant(self):
        return bool(eve.session.corprole & (const.corpRoleJuniorAccountant | const.corpRoleAccountant))

    def AmAccountantOrTrader(self):
        return bool(eve.session.corprole & (const.corpRoleAccountant | const.corpRoleTrader))

    def HaveAccessToCorpWallet(self):
        return bool(self.AmAccountantOrJuniorAccountant() or self.GetAccessibleWallets())

    def HaveAccessToCorpWalletDivision(self, division):
        if division is None:
            return False
        return bool(eve.session.corprole & self.corpWalletRoles[division])

    def HaveReadAccessToCorpWalletDivision(self, division):
        if division is None:
            return False
        return bool(eve.session.corprole & self.corpWalletRoles[division])

    def GetAccessibleWallets(self):
        return filter(self.HaveAccessToCorpWalletDivision, self.corpWalletRoles)

    def GetWnd(self, new = 0):
        resetShowWelcomeToTrue = False
        try:
            wnd = form.Wallet.GetIfOpen()
            if not wnd and new:
                if self.blockWelcomeOnDivisionChange and settings.char.ui.Get('showWelcomPages', 1) == 1:
                    resetShowWelcomeToTrue = True
                    settings.char.ui.Set('showWelcomPages', 0)
                wnd = form.Wallet.Open()
            return wnd
        finally:
            if resetShowWelcomeToTrue:
                settings.char.ui.Set('showWelcomPages', 1)
                self.blockWelcomeOnDivisionChange = False

    def Blink(self, mine = 0, subtabname = None, subsubtabname = None):
        if self.maintabs:
            self.maintabs.BlinkPanelByName([localization.GetByLabel('UI/Wallet/WalletWindow/CorporationWallet'), localization.GetByLabel('UI/Wallet/WalletWindow/MyWallet')][mine])
        panel = [self.corpwallet, self.mywallet][mine]
        if panel:
            panel.Blink(subtabname, subsubtabname)

    def OnCloseWnd(self, *args):
        self.Reset()

    def Load(self, key):
        if key == 'settings':
            self.LoadSettings()

    def LoadSettings(self):
        scrolllist = []
        for cfgname, value, label, group in [['notifyAccountChange',
          None,
          localization.GetByLabel('UI/Wallet/WalletWindow/NotifyAccountChange'),
          None],
         ['notifyBillChange',
          None,
          localization.GetByLabel('UI/Wallet/WalletWindow/NotifyBillChange'),
          None],
         ['notifyShareChange',
          None,
          localization.GetByLabel('UI/Wallet/WalletWindow/NotifyShareChange'),
          None],
         ['notifyOrderChange',
          None,
          localization.GetByLabel('UI/Wallet/WalletWindow/NotifyOrderChange'),
          None],
         ['walletBalanceDelay',
          None,
          localization.GetByLabel('UI/Wallet/WalletWindow/WalletBalanceDelay'),
          None],
         ['walletShowCents',
          None,
          localization.GetByLabel('UI/Wallet/WalletWindow/WalletShowCents'),
          None]]:
            data = util.KeyVal()
            data.label = label
            data.checked = [settings.user.ui.Get(cfgname, value) == value, settings.user.ui.Get(cfgname, 1)][group is None]
            data.cfgname = cfgname
            data.retval = value
            data.group = group
            data.OnChange = self.CheckBoxChange
            scrolllist.append(listentry.Get('Checkbox', data=data))

        wnd = self.GetWnd()
        if wnd:
            wnd.sr.settingsscroll.Load(contentList=scrolllist)

    def CheckBoxChange(self, checkbox):
        settings.user.ui.Set(checkbox.data['key'], not settings.user.ui.Get(checkbox.data['key'], 1))

    def SetBalance(self, label, amount, startamount, color, currency, cLeft, showFractions = None):
        start, ndt = blue.os.GetWallclockTime(), 0.0
        if settings.user.ui.Get('walletBalanceDelay', 1):
            while ndt != 1.0:
                if not label or label.destroyed:
                    return
                ndt = min(blue.os.TimeDiffInMs(start, blue.os.GetWallclockTime()) / 1000.0, 1.0)
                money = mathUtil.Lerp(startamount, amount, ndt)
                label.text = localization.GetByLabel('UI/Wallet/WalletWindow/CurrencyDisplay', color=color, currency=FmtWalletCurrency(money, showFractions=showFractions, currency=currency))
                cLeft = max(cLeft, 32 + label.left + label.textwidth)
                blue.pyos.synchro.Yield()

        label.text = localization.GetByLabel('UI/Wallet/WalletWindow/CurrencyDisplay', color=color, currency=FmtWalletCurrency(amount, showFractions=showFractions, currency=currency))


class WalletContainer(uicls.Container):
    __guid__ = 'form.WalletContainer'
    __nonpersistvars__ = ['loaded',
     'currentmoney',
     'itemID',
     'walletshell',
     'moneystatus',
     'shares',
     'isCorpWallet',
     'uixObjectNames',
     'accessDenied',
     'ownerID',
     'invCookie',
     'invReady']

    def init(self):
        self.loaded = 0
        self.currentmoney = 0
        self.itemID = None
        self.walletshell = None
        self.sr.moneystatus = None
        self.sr.divisionheader = None
        self.sr.divisionlabel = None
        self.shares = []
        self.isCorpWallet = 0
        self.uixObjectNames = {}
        self.accessDenied = 0
        self.ownerID = None
        self.invCookie = None
        self.invReady = 0
        self.isDirty = False
        self.sr.myorders = None
        self.sr.journalbatches = []
        self.sr.journalinited = 0
        self.sr.tabs = None
        self.sr.billstabs = None
        self.sr.transactionbatches = []
        self.sr.transactionsinited = 0
        self.sr.divisionsinited = 0
        self.sr.scroll = None
        self.sr.ordersParent = None
        self.sr.lastJournalData = ([],
         [],
         uiconst.UI_HIDDEN,
         uiconst.UI_HIDDEN)
        self.sr.lastTransactionData = ([],
         [],
         uiconst.UI_HIDDEN,
         uiconst.UI_HIDDEN)

    def TransferMoney(self, fromID, fromAccountKey, toID, toAccountKey):
        sm.GetService('wallet').TransferMoney(fromID, fromAccountKey, toID, toAccountKey)

    def SelectWalletDivision(self, *args):
        sm.GetService('wallet').SelectWalletDivision()

    def Startup(self, isCorpWallet = 0):
        if isCorpWallet:
            btns = [[localization.GetByLabel('UI/Wallet/WalletWindow/GiveMoney'),
              self.TransferMoney,
              (eve.session.charid,
               None,
               eve.session.corpid,
               eve.session.corpAccountKey),
              66]]
            w = 60
            self.accessDenied = not sm.GetService('wallet').HaveReadAccessToCorpWalletDivision(eve.session.corpAccountKey)
            if sm.GetService('wallet').HaveAccessToCorpWalletDivision(eve.session.corpAccountKey):
                btns.append([localization.GetByLabel('UI/Wallet/WalletWindow/TakeMoney'),
                 self.TransferMoney,
                 (eve.session.corpid,
                  eve.session.corpAccountKey,
                  eve.session.charid,
                  None),
                 66])
                btns.append([localization.GetByLabel('UI/Wallet/WalletWindow/TransferMoney'),
                 self.TransferMoney,
                 (eve.session.corpid,
                  eve.session.corpAccountKey,
                  None,
                  None),
                 66])
            if len(sm.GetService('wallet').GetAccessibleWallets()) >= 1:
                btns.append([localization.GetByLabel('UI/Wallet/WalletWindow/ChangeDivision'),
                 self.SelectWalletDivision,
                 None,
                 66])
            self.ownerID = eve.session.corpid
            b = uicls.ButtonGroup(btns=btns, align=uiconst.TOPRIGHT, top=self.push.height, left=6, parent=self, line=0)
            self.push.height += b.height
            self.automaticPaymentSettings = sm.RemoteSvc('billMgr').GetAutomaticPaySettings()
        else:
            self.ownerID = eve.session.charid
        self.isCorpWallet = isCorpWallet
        self.walletshell = None
        self.sr.moneystatus = uiutil.GetChild(self, 'moneystatus')
        self.sr.moneystatus.text = localization.GetByLabel('UI/Wallet/WalletWindow/ZeroBalance')
        self.sr.moneystatus.data = {'amount': 0}
        if not self.isCorpWallet:
            self.sr.aurstatus = uiutil.GetChild(self, 'aurstatus')
            self.sr.aurstatus.text = localization.GetByLabel('UI/Wallet/WalletWindow/ZeroBalance')
            self.sr.aurstatus.data = {'amount': 0}
        if isCorpWallet:
            self.sr.divisionheader = uiutil.GetChild(self, 'divisionheader')
            self.sr.divisionlabel = uiutil.GetChild(self, 'divisionlabel')
        if self.accessDenied:
            self.sr.moneystatus.text = localization.GetByLabel('UI/Wallet/WalletWindow/AccessDenied')
            self.loaded = 1
            return
        uthread.new(self.RegisterWallet)
        self.Register()
        sm.GetService('neocom').BlinkOff('wallet')

    def SetHint(self, hintstr = None):
        if self.sr.scroll is not None:
            self.sr.scroll.ShowHint(hintstr)

    def _OnClose(self, *etc):
        self.Unregister()
        self.Unload()

    def Register(self):
        self.invReady = 1
        self.invCookie = sm.GetService('inv').Register(self)

    def Unregister(self):
        self.invReady = 0
        if getattr(self, 'invCookie', None) is not None:
            sm.GetService('inv').Unregister(self.invCookie)
            self.invCookie = None

    def IsItemHere(self, item):
        return item.ownerID == self.ownerID and item.locationID == const.locationAbstract

    def OnInvChange(self, item, change):
        t = uthread.new(self.OnInvChange_thread, item, change)
        t.context = 'WalletContainer::OnInvChange'

    def OnInvChange_thread(self, item, change):
        if item.groupID == const.groupVoucher and self.sr.tabs and self.sr.tabs.GetSelectedArgs() == 'shares':
            pass

    def CanChangeActiveDivision(self):
        return len(sm.GetService('wallet').GetAccessibleWallets()) >= 1

    def Load(self, args):
        if self.sr.scroll:
            self.sr.scroll.Load(contentList=[])
        if args in ('mywallet', 'corpwallet'):
            isCorpWallet = args == 'corpwallet'
            isMasterWallet = session.corpAccountKey == 1000 and isCorpWallet
            if not self.sr.Get('inited', 0):
                self.sr.inited = 1
                self.push = uicls.Container(name='push', parent=self, align=uiconst.TOTOP, idx=0)
                b = uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/Balance'), parent=self, align=uiconst.TOPRIGHT, left=16, top=6, state=uiconst.UI_DISABLED, bold=True)
                t = uicls.EveLabelLarge(text=localization.GetByLabel('UI/Wallet/WalletWindow/ZeroBalance'), parent=self, name='moneystatus', align=uiconst.TOPRIGHT, state=uiconst.UI_DISABLED, left=16, top=b.top + b.height)
                if args != 'corpwallet':
                    aurLabel = uicls.EveLabelLarge(text=localization.GetByLabel('UI/Wallet/WalletWindow/FmtAUR', aurum=0), parent=self, name='aurstatus', align=uiconst.TOPRIGHT, state=uiconst.UI_DISABLED, left=16, top=t.top + t.height)
                    self.push.height = aurLabel.top + aurLabel.height
                else:
                    self.push.height = t.top + t.height
                self.activeDivHeader = None
                self.activeDivLbl = None
                if args == 'corpwallet':
                    k = getattr(eve.session, 'corpAccountKey')
                    if not k or not sm.GetService('wallet').HaveReadAccessToCorpWalletDivision(k):
                        division = localization.GetByLabel('UI/Wallet/WalletWindow/NoDivisionSelected')
                    else:
                        division = sm.GetService('corp').GetDivisionNames()[k + 8 - 1000]
                    activeDivHeader = uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/ActiveWalletDivision'), parent=self, name='divisionheader', left=12, top=6, state=uiconst.UI_DISABLED, bold=True)
                    activeDivLbl = uicls.EveLabelLarge(text=division, parent=self, name='divisionlabel', width=180, state=uiconst.UI_DISABLED, left=activeDivHeader.left, top=activeDivHeader.top + activeDivHeader.height)
                self.sr.journalOptions = uicls.Container(name='journalOptions', parent=self, align=uiconst.TOTOP, height=34, idx=1)
                self.sr.scroll = uicls.Scroll(parent=self, idx=2, padding=(const.defaultPadding,
                 const.defaultPadding,
                 const.defaultPadding,
                 const.defaultPadding), state=uiconst.UI_HIDDEN)
                maintabs = []
                if isCorpWallet:
                    myOrCorp = 'corp'
                else:
                    myOrCorp = 'my'
                if sm.GetService('wallet').AmAccountantOrJuniorAccountant():
                    tabs = [[localization.GetByLabel('UI/Wallet/WalletWindow/TabPayable'),
                      self.sr.scroll,
                      self,
                      'billsIn'], [localization.GetByLabel('UI/Wallet/WalletWindow/TabReceivable'),
                      self.sr.scroll,
                      self,
                      'billsOut'], [localization.GetByLabel('UI/Wallet/WalletWindow/TabAutomaticallyPaid'),
                      self.sr.scroll,
                      self,
                      'automaticallyPaid']]
                    if isCorpWallet:
                        tabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabAutomaticPaySettings'),
                         self.sr.scroll,
                         self,
                         'automaticpayment'])
                        self.sr.billstabs = uicls.TabGroup(name='tabparent', parent=self, idx=1)
                        self.sr.billstabs.Startup(tabs, '%sbills' % myOrCorp, autoselecttab=0)
                        maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabBills'),
                         self.sr.scroll,
                         self,
                         'bills',
                         self.sr.billstabs])
                self.sr.sharestabs = None
                if not isCorpWallet or sm.GetService('wallet').AmAccountantOrTrader():
                    maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabJournal'),
                     self.sr.scroll,
                     self,
                     'journal',
                     self.sr.journalOptions])
                if not isCorpWallet:
                    maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabShares'),
                     self.sr.scroll,
                     self,
                     'shares',
                     self.sr.sharestabs])
                elif sm.GetService('wallet').AmAccountantOrJuniorAccountant():
                    tabs = [[localization.GetByLabel('UI/Wallet/WalletWindow/TabOwnedByCorp'),
                      self.sr.scroll,
                      self,
                      'shares_ownedby'], [localization.GetByLabel('UI/Wallet/WalletWindow/TabShareholders'),
                      self.sr.scroll,
                      self,
                      'shares_shareholders']]
                    self.sr.sharestabs = uicls.TabGroup(name='tabparent', parent=self, idx=1)
                    self.sr.sharestabs.Startup(tabs, 'shares', autoselecttab=0)
                    maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabShares'),
                     self.sr.scroll,
                     self,
                     'shares',
                     self.sr.sharestabs])
                if args == 'mywallet':
                    self.sr.ordersParent = form.MarketOrders(name='ordersParent', parent=self, align=uiconst.TOALL, pos=(const.defaultPadding,
                     const.defaultPadding,
                     const.defaultPadding,
                     const.defaultPadding), state=uiconst.UI_HIDDEN)
                    maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/Orders'),
                     self.sr.ordersParent,
                     self,
                     'orders'])
                if isCorpWallet:
                    if sm.GetService('wallet').AmAccountantOrJuniorAccountant():
                        maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabWalletDivisions'),
                         self.sr.scroll,
                         self,
                         'divisions'])
                if not isCorpWallet or sm.GetService('wallet').AmAccountantOrTrader():
                    self.sr.transactionsOptions = uicls.Container(name='transactionsOptions', parent=self, align=uiconst.TOTOP, height=34, idx=1)
                    maintabs.append([localization.GetByLabel('UI/Wallet/WalletWindow/TabTransactions'),
                     self.sr.scroll,
                     self,
                     'transactions',
                     self.sr.transactionsOptions])
                self.Startup(args == 'corpwallet')
                if len(maintabs) > 0:
                    self.sr.tabs = uicls.TabGroup(name='tabparent', parent=self, idx=1)
                    self.sr.tabs.Startup(maintabs, args, autoselecttab=0)
                self.sr.buttons = uicls.ButtonGroup(btns=[(localization.GetByLabel('UI/Wallet/WalletWindow/PayBill'),
                  self.PayBillClick,
                  (),
                  84)], parent=self, idx=0, state=uiconst.UI_HIDDEN)
                self.sr.automaticPaybuttons = uicls.ButtonGroup(btns=[(localization.GetByLabel('UI/Wallet/WalletWindow/Submit'),
                  self.SubmitAutomaticPaymentSettings,
                  (),
                  84)], parent=self, idx=0, state=uiconst.UI_HIDDEN)
                uthread.new(self.AskSetWalletDivision)
            if not hasattr(settings.user.tabgroups, args):
                settings.user.tabgroups.Set(args, 3)
            if self.sr.tabs is not None:
                self.sr.tabs.AutoSelect()
            return
        self.SetHint()
        if args in ('bills',):
            if self.sr.scroll is not None:
                self.sr.scroll.sr.id = WALLET_BILLS_SCROLLID
            self.sr.billstabs.AutoSelect()
            return
        if args == 'billsIn':
            self.ShowBillsIn()
        elif args == 'billsOut':
            self.ShowBillsOut()
        elif args == 'automaticallyPaid':
            self.ShowAutomaticallyPaid()
        elif args == 'mybillsreceivable':
            self.ShowMyBills('mybillsreceivable', 'receivable')
        elif args == 'mybillspayable':
            self.ShowMyBills('mybillspayable', 'payable')
        elif args == 'automaticpayment':
            self.ShowAutomaticPaymentOptions()
        elif args == 'shares':
            if self.sr.Get('sharestabs', None):
                self.sr.sharestabs.AutoSelect()
                return
            self.ShowMyShares()
        elif args == 'shares_ownedby':
            self.ShowMyShares()
        elif args == 'shares_shareholders':
            self.ShowShareholders()
        elif args == 'journal':
            if self.sr.scroll is not None:
                self.sr.scroll.sr.id = WALLET_JOURNAL_SCROLLID
            if not self.sr.journalinited:
                self.sr.journalinited = 1
                toppar = self.sr.journalOptions
                sidepar = uicls.Container(name='sidepar', align=uiconst.TOPRIGHT, parent=toppar, left=const.defaultPadding, top=const.defaultPadding, width=54, height=30)
                btn = uix.GetBigButton(24, sidepar, 4, 6)
                btn.OnClick = (self.BrowseJournal, -1)
                btn.hint = localization.GetByLabel('UI/Common/Previous')
                btn.state = uiconst.UI_HIDDEN
                btn.sr.icon.LoadIcon('ui_23_64_1')
                self.sr.journalBackBtn = btn
                btn = uix.GetBigButton(24, sidepar, 28, 6)
                btn.OnClick = (self.BrowseJournal, 1)
                btn.hint = localization.GetByLabel('UI/Common/ViewMore')
                btn.state = uiconst.UI_HIDDEN
                btn.sr.icon.LoadIcon('ui_23_64_2')
                self.sr.journalFwdBtn = btn
                inpt = uicls.SinglelineEdit(name='fromdate', parent=toppar, setvalue=self.GetNow(), align=uiconst.TOPLEFT, left=5, top=16, maxLength=16, label=localization.GetByLabel('UI/Common/Date'))
                inpt.AutoFitToText()
                self.sr.journal_fromdate = inpt
                keylist = []
                reflist = []
                SKIP_REF_TYPES = [const.refATMWithdraw,
                 const.refATMDeposit,
                 const.refBackwardCompatible,
                 const.refFactorySlotRentalFee,
                 18,
                 const.refMissionExpiration,
                 const.refMissionCompletion,
                 const.refCourierMissionEscrow,
                 const.refMissionCost,
                 const.refAgentDonation,
                 const.refAgentSecurityServices,
                 32,
                 const.refCSPAOfflineRefund,
                 43,
                 const.refMarketFinePaid,
                 45,
                 47,
                 const.refTransactionTax,
                 const.refDuplicating,
                 const.refReverseEngineering]
                for refType in sm.GetService('account').GetEntryTypes():
                    if refType.entryTypeID not in SKIP_REF_TYPES and refType.entryTypeID < const.refMaxEve:
                        reflist.append((refType.entryTypeName.lower(), [refType.entryTypeName, refType.entryTypeID]))

                reflist = uiutil.SortListOfTuples(reflist)
                if self.isCorpWallet:
                    divisions = sm.GetService('corp').GetDivisionNames()
                    for key, desc in zip(sm.GetService('account').GetKeyMap(), [ divisions[i] for i in xrange(8, 15) ]):
                        if key.keyID == session.corpAccountKey or eve.session.corprole & (const.corpRoleAccountant | const.corpRoleJuniorAccountant):
                            keylist.append([desc, key.keyID])

                else:
                    map = sm.GetService('account').GetKeyMap()[0]
                    keylist.append((map.keyName, [map.keyName, map.keyID]))
                    keylist = uiutil.SortListOfTuples(keylist)
                lst = [(keylist,
                  localization.GetByLabel('UI/Wallet/WalletWindow/AccountKey'),
                  'accountkey',
                  1000), ([[localization.GetByLabel('UI/Wallet/WalletWindow/AccountKeyAllTypes'), None]] + reflist,
                  localization.GetByLabel('UI/Wallet/WalletWindow/AccountKeyReferenceType'),
                  'accountreftype',
                  None)]
                if not self.isCorpWallet:
                    lst = lst[1:]
                left = inpt.left + inpt.width + 4
                for i, (optlist, label, config, defval) in enumerate(lst):
                    combo = uicls.Combo(label=label.replace('Reference', 'Ref.'), parent=toppar, options=optlist, name=config, select=settings.user.ui.Get(config, defval), callback=self.OnJournalComboChange, width=110, pos=(left,
                     inpt.top,
                     0,
                     0), align=uiconst.TOPLEFT)
                    self.sr.Set('journal_' + config, combo)
                    left += (i + 1) * 114

                if not self.isCorpWallet:
                    currency = settings.user.ui.Get('wallet_personal_currency', const.creditsISK)
                    cbCont = uicls.Container(name='cbCont', parent=toppar, align=uiconst.TOPLEFT, pos=(left + 12,
                     inpt.top,
                     90,
                     20))
                    self.iskCB = uicls.Checkbox(text=localization.GetByLabel('UI/Wallet/WalletWindow/ISK'), parent=cbCont, configName='iskCB', retval=const.creditsISK, checked=currency == const.creditsISK, groupname='walletCurrency', pos=(0, 0, 100, 0), align=uiconst.TOPLEFT, callback=self.OnPersonalWalletCurrencyChanged)
                    self.aurCB = uicls.Checkbox(text=localization.GetByLabel('UI/Wallet/WalletWindow/AUR'), parent=cbCont, configName='aurCB', retval=const.creditsAURUM, checked=currency == const.creditsAURUM, groupname='walletCurrency', pos=(40, 0, 100, 0), align=uiconst.TOPLEFT, callback=self.OnPersonalWalletCurrencyChanged)
                self.sr.journalloadbutton = uicls.Button(parent=toppar, label=localization.GetByLabel('UI/Wallet/WalletWindow/BtnLoad'), pos=(const.defaultPadding,
                 0,
                 0,
                 0), func=self.LoadJournal, align=uiconst.BOTTOMRIGHT)
                sidepar.left = self.sr.journalloadbutton.width + const.defaultPadding
            if self.sr.Get('buttons'):
                self.sr.buttons.state = uiconst.UI_HIDDEN
            if self.sr.Get('automaticPaybuttons'):
                self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
            if self.isCorpWallet and not (const.corpRoleAccountant | const.corpRoleJuniorAccountant) & eve.session.corprole != 0:
                self.sr.scroll.Clear()
                self.sr.journalBackBtn.state = uiconst.UI_HIDDEN
                self.sr.journalFwdBtn.state = uiconst.UI_HIDDEN
                self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountantRoles'))
            else:
                self.sr.scroll.Load(contentList=self.sr.lastJournalData[0], reversesort=1, headers=self.sr.lastJournalData[1])
                self.sr.journalBackBtn.state = self.sr.lastJournalData[2]
                self.sr.journalFwdBtn.state = self.sr.lastJournalData[3]
                if not self.sr.scroll.GetNodes():
                    self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintClickLoadToFetch'))
            uicore.registry.SetFocus(self.sr.journalloadbutton)
        elif args == 'orders':
            self.ShowOrders()
        elif args == 'transactions':
            if self.sr.scroll is not None:
                self.sr.scroll.sr.id = WALLET_TRANSACTIONS_SCROLLID
            if self.sr.Get('buttons'):
                self.sr.buttons.state = uiconst.UI_HIDDEN
            if self.sr.Get('automaticPaybuttons'):
                self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
            if not self.sr.transactionsinited:
                self.sr.buttons.state = uiconst.UI_HIDDEN
                self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
                toppar = self.sr.transactionsOptions
                sidepar = uicls.Container(name='sidepar', align=uiconst.TOPRIGHT, parent=toppar, left=const.defaultPadding, top=const.defaultPadding, width=54, height=30)
                btn = uix.GetBigButton(24, sidepar, 4, 6)
                btn.OnClick = (self.BrowseTransactions, -1)
                btn.hint = localization.GetByLabel('UI/Common/Previous')
                btn.sr.icon.LoadIcon('ui_23_64_1')
                self.sr.transBackBtn = btn
                btn = uix.GetBigButton(24, sidepar, 28, 6)
                btn.OnClick = (self.BrowseTransactions, 1)
                btn.hint = localization.GetByLabel('UI/Common/ViewMore')
                btn.sr.icon.LoadIcon('ui_23_64_2')
                self.sr.transFwdBtn = btn
                self.sr.transactionsinited = 1
                filters_cont = uicls.Container(name='filters_cont', parent=toppar, height=28, align=uiconst.TOTOP, idx=1)
                self.sr.transfilters_cont = filters_cont
                left = 5
                top = 16
                buySellOptions = [(localization.GetByLabel('UI/Wallet/WalletWindow/ComboBoth'), None), (localization.GetByLabel('UI/Wallet/WalletWindow/ComboBuy'), 1), (localization.GetByLabel('UI/Wallet/WalletWindow/ComboSell'), 0)]
                self.sr.transactions_sellbuy = c = uicls.Combo(label=localization.GetByLabel('UI/Wallet/WalletWindow/ComboBuySellLabel'), parent=filters_cont, options=buySellOptions, name='accountkey', pos=(left,
                 top,
                 70,
                 0), adjustWidth=1)
                left += c.width + 4
                if self.isCorpWallet:
                    if sm.GetService('wallet').AmAccountantOrJuniorAccountant():
                        accountOptions = [(localization.GetByLabel('UI/Wallet/WalletWindow/ComboALL'), None)]
                    else:
                        accountOptions = []
                    names = sm.GetService('corp').GetDivisionNames()
                    for i, n in names.iteritems():
                        if i >= 8:
                            accountKey = 1000 + i - 8
                            if sm.GetService('wallet').AmAccountantOrJuniorAccountant() or sm.GetService('wallet').HaveAccessToCorpWalletDivision(accountKey):
                                accountOptions.append((n, accountKey))

                    self.sr.transactions_accountKey = c = uicls.Combo(label=localization.GetByLabel('UI/Wallet/WalletWindow/AccountKey'), parent=filters_cont, options=accountOptions, name='accountkey', width=90, pos=(left,
                     top,
                     0,
                     0))
                    left += c.width + 4
                    self.sr.transactions_who = c = uicls.SinglelineEdit(name='who', parent=toppar, label=localization.GetByLabel('UI/Wallet/WalletWindow/Member'), maxLength=100, pos=(left,
                     top,
                     80,
                     0), adjustWidth=True, isCharacterField=True)
                    left += c.width + 4
                MAX_VAL = 214748364
                self.sr.transactions_qty = c = uicls.SinglelineEdit(name='qty', parent=toppar, label=localization.GetByLabel('UI/Wallet/WalletWindow/MinQty'), maxLength=10, pos=(left,
                 top,
                 70,
                 0), ints=(0, MAX_VAL), setvalue=0, adjustWidth=True)
                left += c.width + 4
                self.sr.transactions_minprice = c = uicls.SinglelineEdit(name='qty', parent=toppar, label=localization.GetByLabel('UI/Wallet/WalletWindow/MinValue'), maxLength=10, pos=(left,
                 top,
                 70,
                 0), ints=(0, MAX_VAL), adjustWidth=True)
                left += c.width + 4
                self.sr.transactions_itemtype = c = uicls.SinglelineEdit(name='type', parent=toppar, label=localization.GetByLabel('UI/Wallet/WalletWindow/ItemType'), pos=(left,
                 top,
                 70,
                 0), adjustWidth=True, isTypeField=True)
                left += c.width + 4
                self.sr.transactionsloadbutton = uicls.Button(parent=toppar, label=localization.GetByLabel('UI/Wallet/WalletWindow/BtnLoad'), func=self.ShowTransactionsFromBtn, pos=(const.defaultPadding,
                 0,
                 0,
                 0), btn_default=1, align=uiconst.BOTTOMRIGHT)
                sidepar.left = self.sr.transactionsloadbutton.width + const.defaultPadding
            if self.isCorpWallet and not (const.corpRoleAccountant | const.corpRoleJuniorAccountant) & eve.session.corprole != 0:
                self.sr.scroll.Clear()
                self.sr.transBackBtn.state = uiconst.UI_HIDDEN
                self.sr.transFwdBtn.state = uiconst.UI_HIDDEN
                self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountantRoles'))
            else:
                self.sr.scroll.Load(contentList=self.sr.lastTransactionData[0], reversesort=1, headers=self.sr.lastTransactionData[1])
                self.sr.transBackBtn.state = self.sr.lastTransactionData[2]
                self.sr.transFwdBtn.state = self.sr.lastTransactionData[3]
                if not self.sr.scroll.GetNodes():
                    self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintClickLoadToFetch'))
            uicore.registry.SetFocus(self.sr.transactionsloadbutton)
        elif args == 'divisions':
            if self.sr.scroll is not None:
                self.sr.scroll.sr.id = WALLET_DIVISIONS_SCROLLID
            if not self.sr.divisionsinited:
                self.sr.buttons.state = uiconst.UI_HIDDEN
                self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
            uthread.new(self.ShowDivisions)
        if self.isDirty:
            self.isDirty = False
            self.GetMoney()

    def OnPersonalWalletCurrencyChanged(self, cb, *args):
        currency = cb.data.get('value', None)
        if currency is None or currency not in (const.creditsISK, const.creditsAURUM):
            return
        currency = settings.user.ui.Set('wallet_personal_currency', currency)
        self.sr.journalBackBtn.state = uiconst.UI_HIDDEN
        self.sr.journalFwdBtn.state = uiconst.UI_HIDDEN
        self.sr.scroll.Load(contentList=[], noContentHint=localization.GetByLabel('UI/Wallet/WalletWindow/HintClickLoadToFetch'))

    def SetAccountKey(self, combo, label, value, *args):
        if value is not None:
            sm.GetService('corp').SetAccountKey(value)

    def AskSetWalletDivision(self):
        sm.StartService('wallet').AskSetWalletDivision()

    def ParseItemType(self, wnd, *args):
        if self.destroyed:
            return
        if not hasattr(self, 'parsingItemType'):
            self.parsingItemType = None
        typeID = DoParseItemType(wnd, self.parsingItemType, True)
        if typeID:
            self.parsingItemType = cfg.invtypes.Get(typeID).name
        return typeID

    def GetIssuer(self, string, exact = 0):
        ownerID = uix.Search(string.lower(), const.groupCharacter, const.categoryOwner, hideNPC=1, filterGroups=[const.groupCharacter], exact=exact, searchWndName='walletIssuerSearch')
        if ownerID:
            return (cfg.eveowners.Get(ownerID).name, ownerID)
        return (string, None)

    def OnJournalComboChange(self, entry, header, value, *args):
        settings.user.ui.Set(entry.name, value)

    def LoadJournal(self, *args):
        self.sr.journalbatches = []
        self.ShowJournal()

    def UpdateBills(self, mine = True):
        if not self.sr.tabs:
            return
        mainTabArgs = self.sr.tabs.GetSelectedArgs()
        if mainTabArgs not in ('bills', 'alliance_bills'):
            return
        billTabArgs = self.sr.billstabs.GetSelectedArgs()
        if billTabArgs == 'billsIn':
            self.ShowBillsIn()
        elif billTabArgs == 'automaticallyPaid':
            self.ShowAutomaticallyPaid()
        elif billTabArgs == 'mybillsreceivable':
            self.ShowMyBills('mybillsreceivable', 'receivable')
        elif billTabArgs == 'mybillspayable':
            self.ShowMyBills('mybillspayable', 'payable')

    def GetBillsPayable(self, ownerID):
        if const.corpRoleAccountant & eve.session.corprole == const.corpRoleAccountant:
            self.sr.buttons.state = uiconst.UI_PICKCHILDREN
        self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
        if ownerID == eve.session.charid:
            return sm.RemoteSvc('billMgr').CharGetBills()
        if util.IsCorporation(ownerID):
            return sm.RemoteSvc('billMgr').GetCorporationBills()
        if util.IsAlliance(ownerID):
            return sm.GetService('alliance').GetBills()

    def GetBillsReceivable(self, ownerID):
        self.sr.buttons.state = uiconst.UI_HIDDEN
        self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
        if ownerID == eve.session.charid:
            bills = sm.RemoteSvc('billMgr').CharGetBillsReceivable()
        elif util.IsCorporation(ownerID):
            bills = sm.RemoteSvc('billMgr').GetCorporationBillsReceivable()
        elif util.IsAlliance(ownerID):
            bills = sm.GetService('alliance').GetBillsReceivable()
        return bills

    def ShowMyBills(self, billID, billType):
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        self.SetHint()
        if billType == 'payable':
            bills = self.GetBillsPayable(eve.session.charid)
            hint = localization.GetByLabel('UI/Wallet/WalletWindow/HintNoPayableBills')
        else:
            bills = self.GetBillsReceivable(eve.session.charid)
            hint = localization.GetByLabel('UI/Wallet/WalletWindow/HintNoReceivableBills')
        if self.destroyed:
            return
        self.DoCfgPrimingForBills(bills)
        scrolllist = []
        for bill in bills:
            data = util.KeyVal()
            label = self.GetTextForBill(bill, data)
            data.bill = bill
            data.groupID = billID
            data.label = label
            data.billPaid = None
            if billType == 'payable':
                data.GetMenu = self.OnPayBillMenu
                scrolllist.append(listentry.Get('Generic', data=data))
            else:
                scrolllist.append(listentry.Get('Generic', data=data))

        if not len(scrolllist):
            self.SetHint(hint)
        self.sr.scroll.Load(contentList=scrolllist, headers=[localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBillType'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'),
         localization.GetByLabel('UI/Common/Date'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderOwedBy'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCreditor'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderInterest')])
        if wnd and not wnd.destroyed:
            wnd.HideLoad()

    def OnPayBillMenu(self, entry):
        if const.corpRoleAccountant & session.corprole == const.corpRoleAccountant:
            entry.DoSelectNode()
            sel = self.sr.scroll.GetSelected()
            if len(sel) > 1:
                text = localization.GetByLabel('UI/Wallet/WalletWindow/MenuPayBills', numBills=len(sel))
            else:
                text = localization.GetByLabel('UI/Wallet/WalletWindow/MenuPayBill')
            return [(text, self.PayBillClick)]
        else:
            return []

    def OnSharesMenu(self, entry):
        m = []
        ownerID = entry.sr.node.ownerID
        corpID = entry.sr.node.corporationID
        shares = entry.sr.node.shares
        if ownerID == eve.session.charid or ownerID == eve.session.corpid and sm.GetService('corp').UserIsActiveCEO():
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuVotes'), self.OpenVotes, (corpID,)))
            m.append(None)
        if ownerID == eve.session.charid or ownerID == eve.session.corpid and const.corpRoleDirector & eve.session.corprole != 0:
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuGiveShares'), self.GiveShares, (ownerID, corpID, shares)))
            m.append(None)
        if util.IsCorporation(ownerID):
            m.append([uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuOwner'), sm.GetService('menu').GetMenuFormItemIDTypeID(ownerID, typeID=const.typeCorporation)])
        else:
            m.append([uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuOwner'), sm.GetService('menu').CharacterMenu(ownerID)])
        m.append([uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuCorporation'), sm.GetService('menu').GetMenuFormItemIDTypeID(corpID, typeID=const.typeCorporation)])
        return m

    def OpenVotes(self, corpID):
        sm.GetService('corpui').VoteWindow(corpID)

    def GiveShares(self, ownerID, corpID, shares):
        form.GiveSharesDialog.CloseIfOpen()
        dlg = form.GiveSharesDialog(corporationID=corpID, maxShares=shares, shareholderID=ownerID)
        dlg.ShowModal()

    def ShowBillsIn(self):
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        bills = []
        if session.allianceid is not None:
            res = self.GetBillsPayable(session.allianceid)
            if res:
                bills.extend(res)
        res = self.GetBillsPayable(session.corpid)
        if res:
            bills.extend(res)
        self.SetHint()
        self.DoCfgPrimingForBills(bills)
        scrolllist = []
        ambSettings = sm.RemoteSvc('billMgr').GetAutomaticPaySettings()
        for bill in bills:
            if bill.debtorID in ambSettings and ambSettings[bill.debtorID].get(bill.billTypeID, False) == True:
                continue
            data = util.KeyVal()
            label = self.GetTextForBill(bill, data)
            data.bill = bill
            data.groupID = bill.billID
            data.label = label
            data.billPaid = None
            data.GetMenu = self.OnPayBillMenu
            scrolllist.append(listentry.Get('Generic', data=data))

        headers = [localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBillType'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'),
         localization.GetByLabel('UI/Common/Date'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderOwedBy'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCreditor'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderInterest'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderItemOrderID')]
        self.sr.scroll.Load(contentList=scrolllist, headers=headers)

    def ShowBillsOut(self):
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        bills = []
        if session.allianceid is not None:
            res = self.GetBillsReceivable(session.allianceid)
            if res:
                bills.extend(res)
        res = self.GetBillsReceivable(session.corpid)
        if res:
            bills.extend(res)
        self.SetHint()
        self.DoCfgPrimingForBills(bills)
        scrolllist = []
        for bill in bills:
            data = util.KeyVal()
            label = self.GetTextForBill(bill, data)
            data.bill = bill
            data.groupID = bill.billID
            data.label = label
            data.billPaid = None
            data.GetMenu = self.OnPayBillMenu
            scrolllist.append(listentry.Get('Generic', data=data))

        headers = [localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBillType'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'),
         localization.GetByLabel('UI/Common/Date'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderOwedBy'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCreditor'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderInterest'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderItemOrderID')]
        self.sr.scroll.Load(contentList=scrolllist, headers=headers)

    def ShowAutomaticallyPaid(self):
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        bills = []
        if session.allianceid is not None:
            res = self.GetBillsPayable(session.allianceid)
            if res:
                bills.extend(res)
        res = self.GetBillsPayable(session.corpid)
        if res:
            bills.extend(res)
        self.SetHint()
        self.DoCfgPrimingForBills(bills)
        scrolllist = []
        ambSettings = sm.RemoteSvc('billMgr').GetAutomaticPaySettings()
        for bill in bills:
            if bill.debtorID not in ambSettings:
                continue
            if ambSettings[bill.debtorID].get(bill.billTypeID, False) == False:
                continue
            data = util.KeyVal()
            label = self.GetTextForBill(bill, data)
            data.bill = bill
            data.groupID = bill.billID
            data.label = label
            data.billPaid = None
            data.GetMenu = self.OnPayBillMenu
            scrolllist.append(listentry.Get('Generic', data=data))

        headers = [localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBillType'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'),
         localization.GetByLabel('UI/Common/Date'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderOwedBy'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCreditor'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderInterest'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderItemOrderID')]
        self.sr.scroll.Load(contentList=scrolllist, headers=headers)

    def GetTextForBill(self, bill, data):
        billTypeName = cfg.billtypes.Get(bill.billTypeID).billTypeName
        text = [billTypeName,
         '<t>',
         FmtWalletCurrency(bill.amount, const.creditsISK),
         '<t>',
         localization.GetByLabel('UI/Wallet/WalletWindow/FmtWalletDate', dt=bill.dueDateTime),
         '<t>',
         cfg.eveowners.Get(bill.debtorID).name,
         '<t>',
         cfg.eveowners.Get(bill.creditorID).name,
         '<t>',
         localization.GetByLabel('UI/Wallet/WalletWindow/FmtInterest', interest=bill.interest)]
        data.Set('sort_%s' % localization.GetByLabel('UI/Common/Date'), (bill.dueDateTime, bill.billID))
        data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'), bill.amount)
        data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderInterest'), bill.interest)
        if bill.billTypeID == const.billTypeMarketFine:
            if bill.externalID != -1 and bill.externalID2 != -1:
                text.append('<t>')
                text.append(cfg.invtypes.Get(bill.externalID).name)
                text.append('<t>')
                text.append(cfg.evelocations.Get(bill.externalID2).name)
            else:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/Something'))
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/SomeMarket'))
        elif bill.billTypeID == const.billTypeRentalBill:
            if bill.externalID != -1 and bill.externalID2 != -1:
                typeID = bill.externalID
                locationID = bill.externalID2
                if typeID == const.typeOfficeFolder:
                    whatOffice = localization.GetByLabel('UI/Wallet/WalletWindow/Office')
                else:
                    whatOffice = cfg.invtypes.Get(typeID).name
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/RentalOffice', whatOffice=whatOffice, location=cfg.evelocations.Get(locationID).name))
            else:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/BillFactoryOrOffice'))
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/SomeStation'))
        elif bill.billTypeID == const.billTypeBrokerBill:
            if bill.externalID != -1 and bill.externalID2 != -1:
                text.append('<t>')
                text.append(bill.externalID)
                text.append('<t>')
                text.append(cfg.evelocations.Get(bill.externalID2).name)
            else:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Generic/Unknown'))
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/Somewhere'))
        elif bill.billTypeID == const.billTypeWarBill:
            if bill.externalID != -1:
                text.append('<t>')
                text.append(cfg.eveowners.Get(bill.externalID).ownerName)
            else:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/Someone'))
        elif bill.billTypeID == const.billTypeAllianceMaintainanceBill:
            if bill.externalID != -1:
                text.append('<t>')
                text.append(cfg.eveowners.Get(bill.externalID).ownerName)
            else:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/SomeAlliance'))
        elif bill.billTypeID == const.billTypeSovereignityMarker:
            if bill.externalID2 != -1:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/SolarSystem', name=cfg.evelocations.Get(bill.externalID2).name))
            else:
                text.append('<t>')
                text.append(localization.GetByLabel('UI/Wallet/WalletWindow/SolarSystem', name=localization.GetByLabel('UI/Wallet/WalletWindow/Somewhere')))
        return text

    def DoCfgPrimingForBills(self, bills):
        if not bills or len(bills) == 0:
            return
        owners = []
        locs = []
        relevantBillTypeIDs = []
        relevantBillTypes = (const.billTypeMarketFine, const.billTypeRentalBill, const.billTypeBrokerBill)
        for billType in sm.GetService('wallet').GetBillTypes().itervalues():
            if billType in relevantBillTypes:
                relevantBillTypeIDs.append(billType.billTypeID)

        for bill in bills:
            for ownerID in (bill.creditorID, bill.debtorID):
                if ownerID not in owners:
                    owners.append(ownerID)

            if bill.billTypeID in relevantBillTypeIDs:
                if bill.externalID != -1 and bill.externalID2 != -1:
                    if bill.externalID2 not in locs:
                        locs.append(bill.externalID2)

        if len(owners):
            cfg.eveowners.Prime(owners)
        if len(locs):
            cfg.evelocations.Prime(locs)

    def PayBillClick(self):
        sel = self.sr.scroll.GetSelected()
        bills = [ (each.groupID, each.bill) for each in sel ]
        for each in bills:
            sm.GetService('wallet').PayBill(each[1])

    def SubmitAutomaticPaymentSettings(self, *args):
        sm.RemoteSvc('billMgr').SendAutomaticPaySettings(self.automaticPaymentSettings)

    def ShowAutomaticPaymentOptions(self):
        if self.sr.Get('buttons'):
            self.sr.buttons.state = uiconst.UI_HIDDEN
        self.sr.automaticPaybuttons.state = uiconst.UI_PICKCHILDREN
        scrolllist = []
        billTypes = sm.GetService('wallet').GetBillTypes()
        for ownerID in self.automaticPaymentSettings:
            for billTypeID, checked in self.automaticPaymentSettings[ownerID].iteritems():
                if billTypeID == 'divisionID':
                    continue
                data = util.KeyVal()
                data.label = cfg.billtypes.Get(billTypeID).billTypeName
                data.checked = checked
                data.OnChange = self.OnAutomaticPaymentChanged
                data.cfgname = cfg.billtypes.Get(billTypeID).billTypeName
                data.retval = (billTypeID, ownerID)
                scrolllist.append(listentry.Get('Checkbox', data=data))

        choices = uiutil.SortListOfTuples([ (acctID, (sm.GetService('corp').GetCorpAccountName(acctID), acctID)) for acctID in sm.GetService('wallet').GetAccessibleWallets() ])
        data = {'options': choices,
         'label': localization.GetByLabel('UI/Wallet/WalletWindow/ComboDivisions'),
         'cfgName': 'divisionID',
         'setValue': self.automaticPaymentSettings.get(session.corpid, {}).get('divisionID', 1000),
         'OnChange': self.OnAutomaticPaymentDivisionChanged,
         'name': 'divisionID'}
        scrolllist.append(listentry.Get('Combo', data))
        self.sr.scroll.Load(contentList=scrolllist)
        sm.GetService('corpui').HideLoad()

    def OnAutomaticPaymentChanged(self, entry):
        billTypeID, ownerID = entry.data['retval']
        if ownerID not in self.automaticPaymentSettings:
            log.LogError('Changing automatic payment settings for an unknown owner', ownerID, billTypeID)
            return
        self.automaticPaymentSettings[ownerID][billTypeID] = bool(entry.checked)

    def OnAutomaticPaymentDivisionChanged(self, combo, header, value, *args):
        if session.corpid not in self.automaticPaymentSettings:
            self.automaticPaymentSettings[session.corpid] = {}
        self.automaticPaymentSettings[session.corpid]['divisionID'] = value

    def GetRentMenu(self, entry):
        stationInfo = sm.GetService('ui').GetStation(entry.sr.node.locationID)
        return sm.GetService('menu').CelestialMenu(entry.sr.node.locationID, typeID=stationInfo.stationTypeID, parentID=stationInfo.solarSystemID)

    def GetRentalSubContent(self, nodedata, *args):
        items = sm.GetService('corp').GetRentalDetailsPlayer()
        scrolllist = []
        for each in items:
            if each.stationID == nodedata.stationID:
                data = util.KeyVal()
                data.info = each
                data.invtype = None
                data.Draggable_blockDrag = 1
                data.viewOnly = 1
                data.viewMode = 0
                scrolllist.append(listentry.Get('JobEntry', data=data))

        return scrolllist

    def ShowJournal(self, browse = None):
        if self.isCorpWallet and not (const.corpRoleAccountant | const.corpRoleJuniorAccountant) & eve.session.corprole != 0:
            self.sr.scroll.Clear()
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountantRoles'))
            return
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        try:
            showingAur = not self.isCorpWallet and self.aurCB.GetValue()
        except:
            showingAur = False
            sys.exc_clear()

        self.sr.journalBackBtn.state = uiconst.UI_HIDDEN
        self.sr.journalFwdBtn.state = uiconst.UI_HIDDEN
        try:
            accountKey = self.sr.journal_accountkey.GetValue()
        except:
            if showingAur:
                accountKey = const.accountingKeyAUR
            else:
                accountKey = 1000
            sys.exc_clear()

        refType = self.sr.journal_accountreftype.GetValue()
        fromDate = self.sr.journal_fromdate.GetValue()
        try:
            fromDate = util.ParseSmallDate(fromDate)
        except (Exception, TypeError):
            fromDate = util.ParseDate(self.GetNow())
            self.sr.journal_fromdate.SetValue(self.GetNow())
            sys.exc_clear()

        aurValues = []
        if browse == -1 and len(self.sr.journalbatches) > 1:
            keyvalues = self.sr.journalbatches[-2]
            self.sr.journalbatches = self.sr.journalbatches[:-1]
        elif browse == 1 and len(self.sr.journalbatches):
            keyvalues = sm.GetService('account').GetJournal(accountKey, fromDate, refType, self.isCorpWallet, self.sr.journalbatches[-1][-1].transactionID, rev=1)
            self.sr.journalBackBtn.state = uiconst.UI_NORMAL
            if len(keyvalues):
                self.sr.journalbatches += [keyvalues]
        else:
            keyvalues = sm.GetService('account').GetJournal(accountKey, fromDate, refType, self.isCorpWallet, rev=1)
            if len(keyvalues):
                self.sr.journalbatches = [keyvalues]
        self.SetHint()
        scrolllist = []
        account = sm.GetService('account')
        displayRecords = []
        for rec in keyvalues:
            if showingAur:
                displayRecords += self._GetDerivedTransactions(rec, const.creditsAURUM)
            else:
                displayRecords += self._GetDerivedTransactions(rec, const.creditsISK)

        originalType = refType
        for rec in displayRecords:
            refType = account.GetRefTypeKeyByID(rec.entryTypeID)
            if originalType and refType.entryTypeID != originalType:
                continue
            elif not refType:
                log.LogWarn('Wallet Journal: No entryType found for entryTypeID', rec.entryTypeID)
                continue
            typeName = refType.entryTypeName
            description = util.FmtRef(rec.entryTypeID, rec.ownerID1, rec.ownerID2, rec.referenceID, amount=rec.amount)
            hintText = self._ParseDescription(rec)
            if hintText:
                description = localization.GetByLabel('UI/Wallet/WalletWindow/HintExtraReference', refText=description)
            if rec.currency == const.creditsAURUM:
                colors = ['<color=0xff05adae>', '<color=0xfff1f202>']
            else:
                colors = ['<color=0xff00ff00>', '<color=0xffff0000>']
            if rec.currency == const.creditsAURUM:
                showFractions = False
            else:
                showFractions = None
            balanceText = FmtWalletCurrency(rec.balance, rec.currency, showFractions=showFractions)
            textList = [util.FmtDate(rec.transactionDate)]
            textList.append(typeName)
            amountString = '<right>%s%s<color=0xffffffff>' % (colors[rec.amount < 0], FmtWalletCurrency(rec.amount, rec.currency, showFractions=showFractions))
            textList.append(amountString)
            balanceString = '<color=0xffffffff>%s' % FmtWalletCurrency(rec.balance, rec.currency, showFractions=showFractions)
            textList.append(balanceString)
            descString = '<left>%s' % description
            textList.append(descString)
            text = '<t>'.join(textList)
            scrolllist.append(listentry.Get('Generic', {'rec': rec,
             'label': text,
             'sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'): rec.amount,
             'sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBalance'): rec.balance,
             'sort_%s' % localization.GetByLabel('UI/Common/Date'): (rec.transactionDate, rec.sortValue),
             'sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCurrency'): rec.currency,
             'hint': hintText}))

        self.sr.scroll.sr.id = WALLET_JOURNAL_SCROLLID
        headers = [localization.GetByLabel('UI/Common/Date'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderType'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBalance'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderDescription')]
        self.sr.scroll.Load(contentList=scrolllist, reversesort=1, headers=headers, noContentHint=localization.GetByLabel('UI/Wallet/WalletWindow/HintNoRecordsFound'))
        if len(keyvalues) == 25:
            self.sr.journalFwdBtn.state = uiconst.UI_NORMAL
        else:
            self.sr.journalFwdBtn.state = uiconst.UI_HIDDEN
        if len(self.sr.journalbatches) > 1:
            self.sr.journalBackBtn.state = uiconst.UI_NORMAL
        else:
            self.sr.journalBackBtn.state = uiconst.UI_HIDDEN
        self.sr.lastJournalData = (scrolllist[:],
         self.sr.scroll.sr.headers,
         self.sr.journalBackBtn.state,
         self.sr.journalFwdBtn.state)
        if wnd and not wnd.destroyed:
            wnd.HideLoad()

    def _ParseDescription(self, transactionRecord):
        if not transactionRecord.description:
            return None
        else:
            try:
                description = yaml.load(transactionRecord.description, Loader=yaml.CSafeLoader)
            except yaml.scanner.ScannerError as e:
                log.LogError('wallet::_ParseDescription: ScannerError: Could not parse wallet transaction description:', transactionRecord.description)
                sys.exc_clear()
                return None

            if type(description) == types.DictType:
                hintLines = []
                if const.refBountyReimbursement == transactionRecord.entryTypeID:
                    ownerIDs = description[const.recDescOwners].split(',')
                    if description.get(const.recDescOwnersTrunc, 0):
                        return localization.GetByLabel('UI/Wallet/WalletWindow/HintBountyReimbursedTruncated', ownerList=localizationUtil.FormatGenericList((cfg.eveowners.Get(ownerID).ownerName for ownerID in ownerIDs)), others=description.get(const.recDescOwnersTrunc, 0))
                    else:
                        return localization.GetByLabel('UI/Wallet/WalletWindow/HintBountyReimbursed', ownerList=localizationUtil.FormatGenericList((cfg.eveowners.Get(ownerID).ownerName for ownerID in ownerIDs), useConjunction=True))
                if const.refBountyPrize:
                    try:
                        ownerIDs = description[const.recDescOwners].split(',')
                    except KeyError:
                        pass
                    else:
                        if description.get(const.recDescOwnersTrunc, 0):
                            return localization.GetByLabel('UI/Wallet/WalletWindow/HintBountyPaidTruncated', ownerList=localizationUtil.FormatGenericList((cfg.eveowners.Get(ownerID).ownerName for ownerID in ownerIDs)), others=description.get(const.recDescOwnersTrunc, 0))
                        return localization.GetByLabel('UI/Wallet/WalletWindow/HintBountyPaid', ownerList=localizationUtil.FormatGenericList((cfg.eveowners.Get(ownerID).ownerName for ownerID in ownerIDs), useConjunction=True))

                if const.recDescription in description:
                    hintLines.append(description[const.recDescription])
                if const.recDescNpcBountyList in description:
                    for typeID, numVictims in description.get(const.recDescNpcBountyList, {}).iteritems():
                        hintLines.append(cfg.invtypes.Get(typeID).name + ' x ' + str(numVictims))

                    if const.recDescNpcBountyListTruncated in description:
                        hintLines.append(localization.GetByLabel('UI/Wallet/WalletWindow/HintBountyTruncated'))
                if const.recStoreItems in description:
                    hintLines.append(localization.GetByLabel('UI/Wallet/WalletWindow/HintVGpurchase'))
                    for typeID, qty in description.get(const.recStoreItems, []):
                        try:
                            typeName = cfg.invtypes.Get(typeID).name
                        except KeyError as e:
                            log.LogError('wallet::_ParseDescription: KeyError', e)
                            sys.exc_clear()
                            continue

                        hintLines.append(localization.GetByLabel('UI/Wallet/WalletWindow/HintItemNameQty', itemName=typeName, qty=int(qty)))

                if transactionRecord.entryTypeID == const.refPlanetaryConstruction and not hintLines:
                    ccUpgradeReason = ''
                    if 'oldLevel' in description:
                        ccUpgradeReason = localization.GetByLabel('UI/PI/Planet/CommandCenterUpgradeReason', oldLevel=description['oldLevel'], newLevel=description['newLevel'])
                    constructionReason = ''
                    destructionReason = ''
                    if 'constructions' in description:
                        constructionParts = []
                        for typeID, qty in description['constructions'].iteritems():
                            constructionParts.append(localization.GetByLabel('UI/Inventory/QuantityAndName', quantity=qty, name=cfg.invtypes.Get(typeID).name))

                        constructionReason = localization.GetByLabel('UI/PI/Planet/ConstructionReason', planet=transactionRecord.referenceID, constructions='\r\n'.join(constructionParts))
                    if 'destructions' in description:
                        destructionParts = []
                        for groupID, qty in description['destructions'].iteritems():
                            destructionParts.append(localization.GetByLabel('UI/Inventory/QuantityAndName', quantity=qty, name=cfg.invgroups.Get(groupID).name))

                        destructionReason = localization.GetByLabel('UI/PI/Planet/DestructionReason', destructions='\r\n'.join(destructionParts))
                    hintLines.append(localization.GetByLabel('UI/PI/Planet/NetworkUpdateTransactionReason', ccUpgrade=ccUpgradeReason, constructions=constructionReason, destructions=destructionReason))
                hintText = '<br>'.join(hintLines)
                if hintText:
                    return hintText
                return None
            r = []
            if transactionRecord.entryTypeID == const.refBountyPrizes:
                lst = description.split(',')
                for l in lst:
                    if ':' in l:
                        tup = l.split(':')
                        r += ['<br>', localization.GetByLabel('UI/Wallet/WalletWindow/HintOldBountyTypeNameQty', typeName=cfg.invtypes.Get(tup[0]).name, qty=int(tup[1]))]
                    elif l == '...':
                        r += ['<br>', localization.GetByLabel('UI/Wallet/WalletWindow/HintOldBountyTruncated')]

                if len(r) > 4:
                    r = r[:-4]
            else:
                r = description
            return r

    def _GetDerivedTransactions(self, transactionRecord, currency = const.creditsISK):
        keyvalTransaction = util.KeyVal(transactionRecord)
        keyvalTransaction.currency = currency
        keyvalTransaction.sortValue = keyvalTransaction.transactionID
        if keyvalTransaction.entryTypeID == const.refBountySurcharge:
            keyvalTransaction.sortValue += 0.2
            return [keyvalTransaction]
        description = keyvalTransaction.description
        entryTypeID = keyvalTransaction.entryTypeID
        amount = keyvalTransaction.amount
        derivedTransactions = [keyvalTransaction]
        if not description or self.isCorpWallet:
            return derivedTransactions

        def AddDerivedCorporationTaxTransaction(entryTypeID, corpID, taxAmount, donorCorpID, mlsHintText):
            taxTransaction = keyvalTransaction.copy()
            taxTransaction.amount = -taxAmount
            taxTransaction.sortValue += 0.5
            taxTransaction.ownerID2 = corpID
            corporationName = cfg.eveowners.Get(corpID).name
            surchargePrcentage, surcharge = descriptionDict.get(const.refBountySurcharge, (0, 0))
            taxPercentage = float(taxAmount) / (amount - surcharge + taxAmount) * 100
            if donorCorpID is None:
                taxTransaction.description = localization.GetByLabel(mlsHintText, taxPercentage=taxPercentage, corporationName=corporationName, amountInIsk=FmtWalletCurrency(const.minCorporationTaxAmount, const.creditsISK))
            else:
                donorCorporationName = cfg.eveowners.Get(donorCorpID).name
                taxTransaction.description = localization.GetByLabel(mlsHintText, taxPercentage=taxPercentage, corporationName=corporationName, donorCorporationName=donorCorporationName, amountInIsk=FmtWalletCurrency(const.minCorporationTaxAmount, const.creditsISK))
            taxTransaction.entryTypeID = entryTypeID
            keyvalTransaction.amount += taxAmount
            keyvalTransaction.balance += taxAmount
            derivedTransactions.insert(0, taxTransaction)

        if description:
            try:
                descriptionDict = yaml.load(description, Loader=yaml.CSafeLoader)
                if type(descriptionDict) == types.DictType:
                    if const.refCorporationTaxNpcBounties in descriptionDict:
                        AddDerivedCorporationTaxTransaction(const.refCorporationTaxNpcBounties, descriptionDict[const.refCorporationTaxNpcBounties][0], descriptionDict[const.refCorporationTaxNpcBounties][1], None, 'UI/Wallet/WalletWindow/HintNPCBountyTax')
                    if const.refCorporationTaxAgentRewards in descriptionDict:
                        AddDerivedCorporationTaxTransaction(const.refCorporationTaxAgentRewards, descriptionDict[const.refCorporationTaxAgentRewards][0], descriptionDict[const.refCorporationTaxAgentRewards][1], None, 'UI/Wallet/WalletWindow/HintAgentRewardTax')
                    if const.refCorporationTaxAgentBonusRewards in descriptionDict:
                        AddDerivedCorporationTaxTransaction(const.refCorporationTaxAgentBonusRewards, descriptionDict[const.refCorporationTaxAgentBonusRewards][0], descriptionDict[const.refCorporationTaxAgentBonusRewards][1], None, 'UI/Wallet/WalletWindow/HintAgentBonusRewardTax')
                    if const.refCorporationTaxRewards in descriptionDict:
                        AddDerivedCorporationTaxTransaction(const.refCorporationTaxRewards, descriptionDict[const.refCorporationTaxRewards][0], descriptionDict[const.refCorporationTaxRewards][1], keyvalTransaction.ownerID1, 'UI/Wallet/WalletWindow/HintCorporateTax')
            except yaml.scanner.ScannerError as e:
                log.LogError('wallet::_GetDerivedTransactions: ScannerError: Could not parse wallet transaction description:', description)
                sys.exc_clear()

        return derivedTransactions

    def BrowseJournal(self, backforth, *args):
        self.ShowJournal(backforth)

    def GetNow(self):
        return util.FmtDate(blue.os.GetWallclockTime(), 'sn')

    def ShowOrders(self, *args):
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        if self.sr.Get('buttons'):
            self.sr.buttons.state = uiconst.UI_HIDDEN
        if self.sr.Get('automaticPaybuttons'):
            self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
        if not getattr(self, 'ordersInited', 0):
            self.sr.ordersParent.Setup('wallet')
            self.ordersInited = 1
        self.sr.ordersParent.ShowOrders()
        if wnd and not wnd.destroyed:
            wnd.HideLoad()

    def ShowTransactionsFromBtn(self, *args):
        self.ShowTransactions()

    def ShowTransactions(self, browse = None, refreshing = 0):
        if self.isCorpWallet and not (const.corpRoleAccountant | const.corpRoleJuniorAccountant) & eve.session.corprole != 0:
            self.sr.scroll.Clear()
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountantRoles'))
            return
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        self.sr.transBackBtn.state = uiconst.UI_HIDDEN
        self.sr.transFwdBtn.state = uiconst.UI_HIDDEN
        sellBuy = self.sr.transactions_sellbuy.GetValue()
        typeID = None
        txt = self.sr.transactions_itemtype.GetValue()
        if txt == '':
            typeID = None
        else:
            for t in sm.GetService('contracts').GetMarketTypes():
                if txt.lower() == cfg.invtypes.Get(t.typeID).name.lower():
                    typeID = t.typeID
                    break

            if typeID is None:
                typeID = self.ParseItemType(self.sr.transactions_itemtype)
        clientID = None
        quantity = self.sr.transactions_qty.GetValue()
        if quantity == '':
            quantity = None
        else:
            quantity = int(quantity)
        fromDate = None
        maxPrice = None
        minPrice = self.sr.transactions_minprice.GetValue()
        if minPrice == '':
            minPrice = None
        else:
            minPrice = int(minPrice)
        accountKey = self.sr.Get('transactions_accountKey', None)
        if accountKey:
            accountKey = accountKey.GetValue()
        who = self.sr.Get('transactions_who', None)
        memberID = None
        if who:
            name = who.GetValue()
            if name != '' and name is not None:
                name, memberID = self.GetIssuer(name)
                who.SetValue(name)
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        if self.isCorpWallet:
            getterPrefix = 'Corp'
        else:
            getterPrefix = 'Char'
        if browse == -1 and len(self.sr.transactionbatches) > 1:
            transactions = self.sr.transactionbatches[-2]
            self.sr.transactionbatches = self.sr.transactionbatches[:-1]
        elif browse == 1 and len(self.sr.transactionbatches):
            lastTran = self.sr.transactionbatches[-1][-1]
            if self.isCorpWallet:
                transactions = sm.GetService('marketQuote').GetMarketProxy().CorpGetTransactions(lastTran.transactionID, sellBuy, typeID, clientID, quantity, fromDate, maxPrice, minPrice, accountKey, memberID)
            else:
                transactions = sm.GetService('marketQuote').GetMarketProxy().CharGetTransactions(lastTran.transactionID, sellBuy, typeID, clientID, quantity, fromDate, maxPrice, minPrice)
            self.sr.transBackBtn.state = uiconst.UI_NORMAL
            if len(transactions):
                self.sr.transactionbatches += [transactions]
        else:
            if self.isCorpWallet:
                transactions = sm.GetService('marketQuote').GetMarketProxy().CorpGetNewTransactions(sellBuy, typeID, clientID, quantity, fromDate, maxPrice, minPrice, accountKey, memberID)
            else:
                transactions = sm.GetService('marketQuote').GetMarketProxy().CharGetNewTransactions(sellBuy, typeID, clientID, quantity, fromDate, maxPrice, minPrice)
            if len(transactions):
                self.sr.transactionbatches = [transactions]
        cfg.eveowners.Prime([ tr.clientID for tr in transactions ])
        if self.isCorpWallet:
            cfg.eveowners.Prime([ tr.characterID for tr in transactions ])
        self.SetHint()
        scrolllist = []
        for tr in transactions:
            hiliteAsCorp = not self.isCorpWallet and tr.corpTransaction
            typeName = cfg.invtypes.Get(tr.typeID).name
            quantity = util.FmtAmt(tr.quantity)
            price = FmtWalletCurrency(tr.price, const.creditsISK)
            location = localization.GetByLabel('UI/Wallet/WalletWindow/StationName', station=tr.stationID)
            when = localization.GetByLabel('UI/Wallet/WalletWindow/FmtWalletDate', dt=tr.transactionDate)
            lines = []
            if hiliteAsCorp:
                coloredWhen = '<color=0xff88bbff>%s</color><color=0xffffffff>' % when
                lines.append(coloredWhen)
            else:
                uncoloredWhen = '%s<color=0xffffffff>' % when
                lines.append(uncoloredWhen)
            if tr.transactionType:
                color = '<color=0xffff0000>'
                sign = -1
            else:
                color = '<color=0xff00ff00>'
                sign = +1
            balance = tr.price * tr.quantity * sign
            client = localization.GetByLabel('UI/Wallet/WalletWindow/CharacterName', charID=tr.clientID)
            lines.append(typeName)
            rightPrice = '<right>%s' % price
            lines.append(rightPrice)
            rightQty = '<right>%s' % quantity
            lines.append(rightQty)
            rightCurrency = '<right>%s%s<color=0xffffffff>' % (color, FmtWalletCurrency(balance, const.creditsISK))
            lines.append(rightCurrency)
            lines.append(localization.GetByLabel('UI/Wallet/WalletWindow/ISK'))
            leftClient = '<left>%s' % client
            lines.append(leftClient)
            leftLocation = '<left>%s' % location
            lines.append(leftLocation)
            if self.isCorpWallet:
                charName = localization.GetByLabel('UI/Wallet/WalletWindow/CharacterName', charID=tr.characterID)
                acctName = sm.GetService('corp').GetCorpAccountName(tr.keyID)
                lines.append(charName)
                lines.append(acctName)
            text = '<t>'.join(lines)
            if hiliteAsCorp:
                hint = '<br><color=0xff88bbff>' + localization.GetByLabel('UI/Wallet/WalletWindow/HintCorpTransaction') + '</color>'
            else:
                hint = ''
            data = util.KeyVal()
            data.rec = tr
            data.label = text
            data.clientID = tr.clientID
            data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderQuantity'), tr.quantity)
            data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderPrice'), tr.price)
            data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWhen'), tr.transactionID)
            data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCredit'), balance)
            if self.isCorpWallet:
                data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWho'), charName)
                data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWalletDivision'), tr.keyID)
            data.hint = hint
            data.GetMenu = self.OnTransactionMenu
            scrolllist.append(listentry.Get('Generic', data=data))

        if len(transactions) >= 25:
            self.sr.transFwdBtn.state = uiconst.UI_NORMAL
        else:
            self.sr.transFwdBtn.state = uiconst.UI_HIDDEN
        if len(self.sr.transactionbatches) > 1:
            self.sr.transBackBtn.state = uiconst.UI_NORMAL
        else:
            self.sr.transBackBtn.state = uiconst.UI_HIDDEN
        headers = [localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWhen'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderType'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderPrice'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderQuantity'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCredit'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCurrency'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderClient'),
         localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWhere')]
        if self.isCorpWallet:
            headers.extend([localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWho'), localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderWalletDivision')])
        if scrolllist:
            self.sr.scroll.sr.id = WALLET_TRANSACTIONS_SCROLLID
            scrollTo = None
            if refreshing:
                scrollTo = self.sr.scroll.GetScrollProportion()
            self.sr.scroll.Load(contentList=scrolllist, reversesort=1, headers=headers, scrollTo=scrollTo)
        elif browse == 1:
            self.sr.scroll.Load(contentList=scrolllist)
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNoMoreTransactions'))
            self.sr.transBackBtn.state = uiconst.UI_NORMAL
        else:
            self.sr.scroll.Load(contentList=scrolllist)
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNoTransactionsFound'))
        self.sr.lastTransactionData = (scrolllist[:],
         self.sr.scroll.sr.headers,
         self.sr.transBackBtn.state,
         self.sr.transFwdBtn.state)
        if wnd and not wnd.destroyed:
            wnd.HideLoad()

    def ShowDivisions(self, force = False):
        if self.sr.scroll:
            self.sr.scroll.Load(contentList=[])
        self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintFetchingDivisions'))
        scrolllist = []
        names = sm.GetService('corp').GetDivisionNames()
        i = 1
        for d in sm.GetService('account').GetWalletDivisionsInfo(force=force):
            data = util.KeyVal()
            label = [localization.GetByLabel('UI/Wallet/WalletWindow/DivisionNameIdx', divName=names[d.key - 1000 + 8], idx=i), '<t>', FmtWalletCurrency(d.balance, const.creditsISK)]
            data.label = label
            data.GetMenu = self.OnDivisionMenu
            data.key = d.key
            data.Set('sort_%s' % localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderDivision'), d.key)
            scrolllist.append(listentry.Get('Generic', data=data))
            i += 1

        scrollTo = None
        if self.sr.tabs and self.sr.tabs.GetSelectedArgs() == 'divisions':
            self.sr.scroll.sr.id = WALLET_DIVISIONS_SCROLLID
            self.sr.scroll.Load(contentList=scrolllist, reversesort=1, headers=[localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderDivision'), localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderBalance')], scrollTo=scrollTo)
            self.SetHint(None)

    def DoSetAccountKey(self, key):
        sm.StartService('wallet').blockWelcomeOnDivisionChange = True
        sm.GetService('corp').SetAccountKey(key)

    def OnDivisionMenu(self, entry):
        m = []
        if sm.GetService('wallet').HaveAccessToCorpWalletDivision(entry.sr.node.key):
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuSetActiveWallet'), lambda : self.DoSetAccountKey(entry.sr.node.key)))
            m.append(None)
        if sm.GetService('wallet').AmAccountantOrTrader():
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuViewJournal'), self.OnDivision_ViewJournal, (entry.sr.node.key,)))
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuViewTransactions'), self.OnDivision_ViewTransactions, (entry.sr.node.key,)))
        if sm.GetService('wallet').HaveAccessToCorpWalletDivision(entry.sr.node.key):
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuTransferToCorp'), self.OnDivision_GiveMoney, (entry.sr.node.key,)))
            m.append((uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuTransferFromCorp'), self.OnDivision_TakeMoney, (entry.sr.node.key,)))
        return m

    def OnDivision_ViewJournal(self, key):
        self.sr.tabs.ShowPanelByName(localization.GetByLabel('UI/Wallet/WalletWindow/TabJournal'))
        self.sr.journal_accountkey.SelectItemByValue(key)
        self.LoadJournal()

    def OnDivision_ViewTransactions(self, key):
        self.sr.tabs.ShowPanelByName(localization.GetByLabel('UI/Wallet/WalletWindow/TabTransactions'))
        self.sr.transactions_accountKey.SelectItemByValue(key)
        self.ShowTransactions()

    def OnDivision_GiveMoney(self, key):
        sm.GetService('wallet').TransferMoney(eve.session.corpid, eve.session.corpAccountKey, eve.session.corpid, key)

    def OnDivision_TakeMoney(self, key):
        sm.GetService('wallet').TransferMoney(eve.session.corpid, key, eve.session.corpid, eve.session.corpAccountKey)

    def OnTransactionMenu(self, entry):
        stationID = entry.sr.node.rec.stationID
        stationInfo = sm.GetService('ui').GetStation(stationID)
        m = sm.GetService('menu').GetMenuFormItemIDTypeID(None, entry.sr.node.rec.typeID, ignoreMarketDetails=0)
        m += [None]
        m += [(uiutil.MenuLabel('UI/Wallet/WalletWindow/MenuLocation'), sm.GetService('menu').CelestialMenu(stationID, typeID=stationInfo.stationTypeID, parentID=stationInfo.solarSystemID))]
        m += [(uiutil.MenuLabel('UI/Wallet/WalletWindow/ColHeaderClient'), sm.GetService('menu').CharacterMenu(entry.sr.node.clientID))]
        return m

    def BrowseTransactions(self, direction, *args):
        self.ShowTransactions(direction)

    def Blink(self, tabname, subtabname):
        if tabname and not self.destroyed and self.sr:
            if self.sr.tabs and not self.sr.tabs.destroyed:
                self.sr.tabs.BlinkPanelByName(tabname)
            if subtabname:
                if self.sr.myorders and not self.sr.myorders.destroyed and getattr(self.sr.myorders.sr, 'tabs', None):
                    self.sr.myorders.sr.tabs.BlinkPanelByName(subtabname)
                if self.sr.billstabs and not self.sr.billstabs.destroyed:
                    self.sr.billstabs.BlinkPanelByName(subtabname)

    def Unload(self):
        if self.walletshell:
            self.walletshell = None

    def GetWallet(self):
        wallet = None
        if not self.accessDenied:
            if self.isCorpWallet:
                wallet = sm.RemoteSvc('corpmgr').GetCorporationWallet(eve.session.corpid)
            else:
                wallet = sm.GetService('invCache').GetInventory(const.containerWallet)
        return wallet

    def ShowMyShares(self, checkvis = 0):
        if self.sr.Get('buttons'):
            self.sr.buttons.state = uiconst.UI_HIDDEN
        if self.sr.Get('automaticPaybuttons'):
            self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
        if self.accessDenied:
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountant'))
            return
        if self.isCorpWallet and not (const.corpRoleAccountant | const.corpRoleJuniorAccountant) & eve.session.corprole != 0:
            self.sr.scroll.Clear()
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountantRoles'))
            return
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        self.SetHint()
        scrolllist = []
        shareCertificates = sm.GetService('corp').GetSharesByShareholder(self.isCorpWallet)
        for shareCertificate in shareCertificates.itervalues():
            if not self or self.destroyed:
                if wnd and hasattr(wnd, 'HideLoad'):
                    wnd.HideLoad()
                return
            data = util.KeyVal()
            data.ownerID = [eve.session.charid, eve.session.corpid][self.isCorpWallet]
            data.corporationID = shareCertificate.corporationID
            data.shares = shareCertificate.shares
            data.GetMenu = self.OnSharesMenu
            data.label = [cfg.eveowners.Get(data.ownerID).name, '<t>']
            data.label += [cfg.eveowners.Get(data.corporationID).name, '<t>']
            data.label += [util.FmtAmt(data.shares)]
            scrolllist.append(listentry.Get('Generic', data=data))

        if self.sr.scroll is not None:
            self.sr.scroll.sr.id = WALLET_SHARES_SCROLLID
        if scrolllist:
            if self.sr.scroll is not None:
                headers = [localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderOwner'), localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCorporation'), localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderShares')]
                self.sr.scroll.Load(fixedEntryHeight=24, contentList=scrolllist, headers=headers)
        else:
            if self.sr.scroll is not None:
                self.sr.scroll.Clear()
            if self.isCorpWallet:
                self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNoCorpShares'))
            else:
                self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNoShares'))
        if wnd:
            wnd.HideLoad()

    def ShowShareholders(self):
        if self.sr.Get('buttons'):
            self.sr.buttons.state = uiconst.UI_HIDDEN
        if self.sr.Get('automaticPaybuttons'):
            self.sr.automaticPaybuttons.state = uiconst.UI_HIDDEN
        if self.accessDenied:
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountant'))
            return
        if self.isCorpWallet and not (const.corpRoleAccountant | const.corpRoleJuniorAccountant) & eve.session.corprole != 0:
            self.sr.scroll.Clear()
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNeedAccountantRoles'))
            return
        wnd = form.Wallet.GetIfOpen()
        if wnd and not wnd.destroyed:
            wnd.ShowLoad()
        else:
            return
        self.SetHint()
        scrolllist = []
        shares = sm.GetService('corp').GetShareholders()
        for shareCertificate in shares.itervalues():
            data = util.KeyVal()
            data.ownerID = shareCertificate.shareholderID
            if shareCertificate.shareholderCorporationID:
                data.corporationID = shareCertificate.shareholderCorporationID
            else:
                data.corporationID = shareCertificate.corporationID
            data.shares = shareCertificate.shares
            data.GetMenu = self.OnSharesMenu
            data.label = [cfg.eveowners.Get(data.ownerID).name,
             '<t>',
             cfg.eveowners.Get(data.corporationID).name,
             '<t>',
             util.FmtAmt(data.shares)]
            scrolllist.append(listentry.Get('Generic', data=data))

        if scrolllist:
            if self.sr.scroll is not None:
                headers = [localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderOwner'), localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderCorporation'), localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderShares')]
                self.sr.scroll.Load(fixedEntryHeight=24, contentList=scrolllist, headers=headers)
        else:
            if self.sr.scroll is not None:
                self.sr.scroll.Clear()
            self.SetHint(localization.GetByLabel('UI/Wallet/WalletWindow/HintNoCorpShares'))
        if wnd:
            wnd.HideLoad()

    def RegisterWallet(self):
        try:
            if self.accessDenied:
                return
            self.GetMoney()
        except:
            wnd = form.Wallet.GetIfOpen()
            if not wnd or wnd.destroyed:
                sys.exc_clear()
                return
            raise 

    def GetShell(self, reload = 0):
        if not self.walletshell or reload:
            self.walletshell = self.GetWallet()
        return self.walletshell

    def GetMoney(self, *args):
        if self.accessDenied:
            return
        wealth = sm.RemoteSvc('account').GetCashBalance(self.isCorpWallet)
        if not self.isCorpWallet:
            aurWealth = sm.RemoteSvc('account').GetCashBalance(self.isCorpWallet, accountKey=const.accountingKeyAUR)
            self.wealth = wealth
            self.aurWealth = aurWealth
            uthread.new(self.SetMoney, aurWealth, currency=const.creditsAURUM)
        uthread.new(self.SetMoney, wealth, currency=const.creditsISK)

    def SetMoney(self, amount, currency = const.creditsISK):
        if self.isCorpWallet and currency == const.creditsAURUM:
            return
        if self.destroyed or self.accessDenied:
            return
        if currency == const.creditsISK and not util.GetAttrs(self, 'sr', 'moneystatus'):
            return
        if currency == const.creditsAURUM and not util.GetAttrs(self, 'sr', 'aurstatus'):
            return
        if self.isCorpWallet and (not util.GetAttrs(self, 'sr', 'divisionlabel') or not util.GetAttrs(self, 'sr', 'divisionheader')):
            return
        showFractions = None
        if currency == const.creditsISK:
            label = self.sr.moneystatus
            self.currentmoney = amount
            color = '<color=0xffaaaaaa>'
        elif currency == const.creditsAURUM:
            label = self.sr.aurstatus
            self.currentAur = amount
            color = '<color=0xff05adae>'
            showFractions = 0
        startamount = label.data['amount']
        label.data['amount'] = amount
        cLeft = 128
        sm.GetService('wallet').SetBalance(label, amount, startamount, color, currency, cLeft, showFractions=showFractions)

    def OnShareChange(self, shareholderID, corporationID, change):
        if not self.sr.Get('tabs', None):
            return
        sharestabs = self.sr.Get('sharestabs', None)
        if sharestabs:
            if sharestabs.GetSelectedArgs() == 'shares_shareholders':
                self.ShowShareholders()
                return
        self.ShowMyShares()


class GiveSharesDialog(uicls.Window):
    __guid__ = 'form.GiveSharesDialog'
    default_windowID = 'GiveSharesDialog'

    def ApplyAttributes(self, attributes):
        uicls.Window.ApplyAttributes(self, attributes)
        corporationID = attributes.corporationID
        maxShares = attributes.maxShares
        shareholderID = attributes.shareholderID
        self.ownerID = None
        self.searchStr = ''
        self.corporationID = corporationID
        self.maxShares = maxShares
        self.shareholderID = shareholderID
        self.scope = 'all'
        self.SetTopparentHeight(80)
        self.SetCaption(localization.GetByLabel('UI/Wallet/WalletWindow/CaptionGiveSharesTo', who=cfg.eveowners.Get(self.shareholderID).name))
        self.SetWndIcon(None)
        self.SetMinSize([400, 130])
        self.sr.standardBtns = uicls.ButtonGroup(btns=[[localization.GetByLabel('UI/Common/Buttons/OK'),
          self.OnOK,
          (),
          81], [localization.GetByLabel('UI/Common/Buttons/Cancel'),
          self.OnCancel,
          (),
          81]])
        self.sr.main.children.insert(0, self.sr.standardBtns)
        left = 80
        uicls.EveCaptionMedium(text=localization.GetByLabel('UI/Wallet/WalletWindow/CaptionGiveShares'), parent=self.sr.topParent, left=left - 1, top=6)
        self.sharesLabel = uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/NumberOfShares'), parent=self.sr.topParent, width=100, left=left, top=32, state=uiconst.UI_NORMAL)
        inptShares = uicls.SinglelineEdit(name='edit', parent=self.sr.topParent, setvalue=self.maxShares, ints=(1, self.maxShares), pos=(self.sharesLabel.left + self.sharesLabel.width + 6,
         self.sharesLabel.top,
         126,
         0), align=uiconst.TOPLEFT, maxLength=32)
        self.sr.inptShares = inptShares
        self.ownerLabel = uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/ToOwner'), parent=self.sr.topParent, width=100, left=left, top=56, state=uiconst.UI_NORMAL)
        inptOwner = uicls.SinglelineEdit(name='edit', parent=self.sr.topParent, pos=(self.sharesLabel.left + self.ownerLabel.width + 6,
         self.ownerLabel.top,
         126,
         0), align=uiconst.TOPLEFT, maxLength=48)
        inptOwner.OnReturn = self.Search
        self.sr.inptOwner = inptOwner
        btn = uicls.Button(parent=self.sr.topParent, label=localization.GetByLabel('UI/Wallet/WalletWindow/BtnSearch'), pos=(inptOwner.left + inptOwner.width + 2,
         inptOwner.top,
         0,
         0), func=self.Search, btn_default=1)
        self.ShowCorpLogo(self.corporationID)
        return self

    def ShowCorpLogo(self, corporationID):
        self.picture = uiutil.GetChild(self, 'mainicon')
        self.picture.left = const.defaultPadding
        self.picture.top = const.defaultPadding
        self.picture.texture = None
        uiutil.GetChild(self, 'clippedicon').Close()
        loc = uicls.Container(name='logoContainer', align=uiconst.TOALL, parent=self.sr.topParent, pos=(const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding))
        if loc is not None:
            uix.Flush(loc)
            logo = uiutil.GetLogoIcon(itemID=corporationID, parent=loc, idx=0, state=uiconst.UI_PICKCHILDREN, size=64, ignoreSize=True)
            if hasattr(logo, 'children'):
                for child in logo.children:
                    child.state = uiconst.UI_DISABLED

    def Search(self, *args):
        self.searchStr = self.sr.inptOwner.GetValue().strip()
        self.ownerID = uix.Search(self.searchStr.lower(), const.groupCharacter, const.categoryOwner, hideNPC=1, filterGroups=[const.groupCharacter, const.groupCorporation], searchWndName='walletSearchSearch', hideDustChars=True)
        if self.ownerID:
            self.sr.inptOwner.SetText(cfg.eveowners.Get(self.ownerID).name)

    def OnOK(self, *args):
        if not self.ownerID:
            self.Search()
        if self.ownerID:
            self.TransferShares(self.ownerID, self.sr.inptShares.GetValue())
            self.CloseByUser()
        else:
            raise UserError('GiveSharesSelectOwner')

    def OnCancel(self, *args):
        self.ownerID = None
        self.CloseByUser()

    def TransferShares(self, toShareholderID, numberOfShares):
        if cfg.eveowners.Get(self.shareholderID).typeID == const.typeCorporation:
            sm.GetService('corp').MoveCompanyShares(self.corporationID, toShareholderID, numberOfShares)
        else:
            sm.GetService('corp').MovePrivateShares(self.corporationID, toShareholderID, numberOfShares)


class WalletWindow(uicls.Window):
    __guid__ = 'form.Wallet'
    default_width = 560
    default_height = 400
    default_minSize = (560, 300)
    default_windowID = 'wallet'
    default_topParentHeight = 0

    def ApplyAttributes(self, attributes):
        uicls.Window.ApplyAttributes(self, attributes)
        self.SetCaption(localization.GetByLabel('UI/Wallet/WalletWindow/Wallet'))
        walletSvc = sm.GetService('wallet')
        self.scope = 'station_inflight'
        self.SetWndIcon('ui_7_64_12', size=128)
        mywallet = WalletContainer(name='mywallet', parent=self.sr.main, state=uiconst.UI_HIDDEN, pos=(0, 0, 0, 0))
        tabs = [[localization.GetByLabel('UI/Wallet/WalletWindow/MyWallet'),
          mywallet,
          mywallet,
          'mywallet']]
        if walletSvc.HaveAccessToCorpWallet():
            corpwallet = WalletContainer(name='corpwallet', parent=self.sr.main, state=uiconst.UI_HIDDEN, pos=(0, 0, 0, 0))
            tabs += [[localization.GetByLabel('UI/Wallet/WalletWindow/CorporationWallet'),
              corpwallet,
              corpwallet,
              'corpwallet']]
        else:
            corpwallet = None
        self.sr.settingsscroll = uicls.Scroll(name='settingsscroll', parent=self.sr.main, padding=(const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding))
        self.sr.settingsscroll.sr.id = 'walletsettings'
        tabs += [[localization.GetByLabel('UI/Wallet/WalletWindow/Settings'),
          self.sr.settingsscroll,
          walletSvc,
          'settings']]
        maintabs = uicls.TabGroup(name='tabparent', parent=self.sr.main, idx=0)
        maintabs.Startup(tabs, 'walletpanel')
        walletSvc.mywallet = mywallet
        walletSvc.corpwallet = corpwallet
        walletSvc.maintabs = maintabs

    def _OnClose(self, *args):
        sm.GetService('wallet').OnCloseWnd(*args)


class TransferMoneyWnd(uicls.Window):
    __guid__ = 'form.TransferMoneyWnd'
    default_windowID = 'TransferMoney'

    def ApplyAttributes(self, attributes):
        uicls.Window.ApplyAttributes(self, attributes)
        self.currency = const.creditsISK
        self.aurColor = '<color=0xff05adae>'
        self.maxISKvalue = 0
        self.minISKvalue = 0.1
        self.fromID = attributes.fromID
        self.fromAccountKey = attributes.fromAccountKey
        self.toID = attributes.toID
        self.toAccountKey = attributes.toAccountKey
        self.isCorpTransfer = bool(util.IsCorporation(self.toID) or util.IsCorporation(self.fromID))
        self.SetCaption(localization.GetByLabel('UI/Wallet/WalletWindow/TransferMoney'))
        self.minHeight = 246
        self.SetMinSize([250, self.minHeight])
        self.MakeUnResizeable()
        self.SetWndIcon()
        self.SetTopparentHeight(0)
        self.walletSvc = sm.GetService('wallet')
        self.ConstructLayout()

    def ConstructLayout(self):
        if self.fromID == session.charid:
            self.maxISKvalue = self.walletSvc.GetWealth()
            showFromAccount = False
        else:
            self.maxISKvalue = self.walletSvc.GetCorpWealth(self.fromAccountKey)
            showFromAccount = True
            if self.fromAccountKey is None:
                self.fromAccountKey = session.corpAccountKey
        if self.toID == session.corpid:
            self.showToAccount = True
        else:
            self.showToAccount = False
        if self.isCorpTransfer:
            showCurrency = False
        else:
            showCurrency = True
        ret = sm.GetService('machoNet').GetGlobalConfig().get('disableTransferAUR')
        if ret is not None and int(ret):
            showCurrency = False
        giverCont = uicls.Container(name='topCont', parent=self.sr.main, align=uiconst.TOTOP, pos=(0, 0, 0, 70), padding=(const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding,
         0))
        giverImgCont = uicls.Container(name='imgCont', parent=giverCont, align=uiconst.TOLEFT, pos=(0, 0, 64, 0), padding=(0,
         0,
         const.defaultPadding,
         0))
        giverCont = uicls.Container(name='topRightCont', parent=giverCont, align=uiconst.TOALL, pos=(0, 0, 0, 0), padding=(const.defaultPadding,
         0,
         0,
         0))
        uiutil.GetOwnerLogo(giverImgCont, self.fromID, size=64, noServerCall=True)
        if showFromAccount:
            label = localization.GetByLabel('UI/Wallet/WalletWindow/FromCharacterAcct', charID=self.fromID, acctName=sm.GetService('corp').GetCorpAccountName(self.fromAccountKey))
        else:
            label = localization.GetByLabel('UI/Wallet/WalletWindow/FromCharacter', charID=self.fromID)
        uicls.EveLabelMedium(text=label, parent=giverCont, left=0, top=0, align=uiconst.CENTERLEFT, width=170, state=uiconst.UI_DISABLED, idx=0)
        receiverCont = uicls.Container(name='bottomCont', parent=self.sr.main, align=uiconst.TOTOP, pos=(0, 0, 0, 70), padding=(const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding,
         const.defaultPadding))
        receiverimgCont = uicls.Container(name='imgCont', parent=receiverCont, align=uiconst.TOLEFT, pos=(0, 0, 64, 0), padding=(0,
         0,
         const.defaultPadding,
         0))
        receiverCont = uicls.Container(name='nameCont', parent=receiverCont, align=uiconst.TOALL, pos=(0, 0, 0, 0), padding=(const.defaultPadding,
         0,
         0,
         0))
        icon = uiutil.GetOwnerLogo(receiverimgCont, self.toID, size=64, noServerCall=True)
        label = localization.GetByLabel('UI/Wallet/WalletWindow/ToCharacter', charID=self.toID)
        uicls.EveLabelMedium(text=label, parent=receiverCont, left=0, top=0, align=uiconst.CENTERLEFT, width=170, state=uiconst.UI_DISABLED, idx=0)
        textLeft = 0
        editLeft = 72
        width = 172
        top = 0
        controlsCont = uicls.Container(name='centerCont', parent=self.sr.main, align=uiconst.TOTOP, pos=(0, 0, 0, 54), padding=(const.defaultPadding,
         0,
         const.defaultPadding,
         0))
        if self.showToAccount:
            opt = []
            for i in self.walletSvc.corpWalletRoles:
                opt.append((sm.GetService('corp').GetCorpAccountName(i), i))

            controlsCont.height += 25
            self.minHeight += 25
            uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/Account'), parent=controlsCont, align=uiconst.TOPLEFT, top=4, left=textLeft)
            self.combo = uicls.Combo(parent=controlsCont, options=opt, name='AccountCombo', select=self.toAccountKey, left=editLeft, width=width)
            top += 25
        uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/ColHeaderAmount'), parent=controlsCont, align=uiconst.TOPLEFT, top=top + 4, left=textLeft)
        self.amount = uicls.SinglelineEdit(name='amount', parent=controlsCont, setvalue='%s' % self.minISKvalue, floats=[self.minISKvalue, float(self.maxISKvalue), 2], align=uiconst.TOPLEFT, left=editLeft, width=width - 22, top=top, autoselect=True)
        self.amount.SetText = self.SetEditText
        self.currencyLabel = uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/ISK'), parent=controlsCont, align=uiconst.TOPLEFT, top=top + 4, left=self.amount.left + self.amount.width + const.defaultPadding)
        if showCurrency:
            currencyHeight = 14
            top += currencyHeight
            controlsCont.height += currencyHeight
            self.minHeight += currencyHeight
            cbCont = uicls.Container(name='cbCont', parent=controlsCont, align=uiconst.TOPRIGHT, pos=(20,
             top + 6,
             90,
             20))
            self.iskCB = uicls.Checkbox(text=localization.GetByLabel('UI/Wallet/WalletWindow/ISK'), parent=cbCont, configName='iskCB', retval=const.creditsISK, checked=1, groupname='currencyRBGroup', callback=self.OnCheckboxChange, pos=(0, 0, 100, 0), align=uiconst.TOPLEFT)
            self.aurCB = uicls.Checkbox(text=localization.GetByLabel('UI/Wallet/WalletWindow/AUR'), parent=cbCont, configName='aurCB', retval=const.creditsAURUM, checked=0, groupname='currencyRBGroup', callback=self.OnCheckboxChange, pos=(50, 0, 100, 0), align=uiconst.TOPLEFT)
        uicls.EveLabelSmall(text=localization.GetByLabel('UI/Wallet/WalletWindow/Reason'), parent=controlsCont, align=uiconst.TOPLEFT, top=top + 29, left=textLeft)
        self.reason = uicls.SinglelineEdit(name='reason', parent=controlsCont, maxLength=40, top=top + 25, align=uiconst.TOPLEFT, left=editLeft, width=width)
        self.btnGroup = uicls.ButtonGroup(btns=[[localization.GetByLabel('UI/Common/Buttons/OK'),
          self.Confirm,
          (),
          81,
          1,
          1,
          0], [localization.GetByLabel('UI/Common/Buttons/Cancel'),
          self.CloseByUser,
          (),
          81,
          0,
          0,
          0]], parent=self.sr.main, idx=0)
        uicore.registry.SetFocus(self.amount)
        uthread.new(self.SetWindowSize)

    def SetWindowSize(self, *args):
        if self and not self.destroyed:
            self.height = self.minHeight
            self.SetMinSize([200, self.minHeight])

    def OnCheckboxChange(self, cb, *args):
        currency = cb.data.get('value', None)
        if currency is None or currency not in (const.creditsISK, const.creditsAURUM):
            return
        if self.isCorpTransfer:
            raise UserError('AurToOrFromCorp')
        self.currency = currency
        amount = self.amount.GetValue()
        if self.currency == const.creditsAURUM:
            self.currencyLabel.text = localization.GetByLabel('UI/Wallet/WalletWindow/AURLabel', color=self.aurColor)
            minvalue = 1
            maxValue = self.walletSvc.GetAurWealth()
            self.amount.IntMode(minvalue, maxValue)
            amount = int(amount)
        else:
            self.currencyLabel.text = localization.GetByLabel('UI/Wallet/WalletWindow/ISK')
            self.amount.FloatMode(self.minISKvalue, self.maxISKvalue)
        self.amount.SetValue(amount)

    def SetEditText(self, text, format = 0):
        uicls.SinglelineEdit.SetText(self.amount, text, format)
        if self.currency == const.creditsAURUM:
            text = self.amount.sr.text.text
            self.amount.sr.text.text = '%s%s' % (self.aurColor, text)

    def Confirm(self, *args):
        toAccountKey = None
        fromAccountKey = None
        amount = self.amount.GetValue()
        reason = self.reason.GetValue()
        if amount <= 0:
            return
        if getattr(self, 'aurCB', None) and self.aurCB.GetValue():
            if self.isCorpTransfer:
                raise UserError('AurToOrFromCorp')
            toAccountKey = const.accountingKeyAUR
            fromAccountKey = const.accountingKeyAUR
        if self.showToAccount:
            toAccountKey = self.combo.GetValue()
        if self.fromID == session.charid:
            sm.RemoteSvc('account').GiveCash(self.toID, amount, reason, toAccountKey=toAccountKey)
        else:
            sm.RemoteSvc('account').GiveCashFromCorpAccount(self.toID, amount, self.fromAccountKey, toAccountKey=toAccountKey, reason=reason)
        self.CloseByUser()