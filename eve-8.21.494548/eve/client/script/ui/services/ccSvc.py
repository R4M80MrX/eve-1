#Embedded file name: c:/depot/games/branches/release/EVE-TRANQUILITY/eve/client/script/ui/services/ccSvc.py
import service
import copy
import random
import util
import uiutil
import telemetry
import uthread
import log

class CCSvc(service.Service):
    __update_on_reload__ = 1
    __guid__ = 'svc.cc'
    __exportedcalls__ = {}
    __dependencies__ = ['invCache']

    def __init__(self):
        service.Service.__init__(self)

    def Run(self, *etc):
        service.Service.Run(self, *etc)
        util.LookupConstValue('', '')
        self.chars = None
        self.charCreationInfo = None
        self.raceData, self.raceDataByID = (None, None)
        self.bloodlineDataByRaceID, self.bloodlineDataByID = (None, None)
        self.dollState = None
        self.availableTypeIDs = None

    def GetCharactersToSelect(self, force = 0):
        self.LogInfo('CC::GetCharactersToSelect::force=%s' % force)
        if self.chars is None or force:
            chars = sm.RemoteSvc('charUnboundMgr').GetCharactersToSelect()
            self.chars = util.Rowset(chars.columns, list(chars))
        return self.chars

    def GetCharCreationInfo(self):
        if self.charCreationInfo is None:
            uthread.Lock(self)
            try:
                if self.charCreationInfo is None:
                    o = uiutil.Bunch()
                    o.update(sm.RemoteSvc('charUnboundMgr').GetCharCreationInfo())
                    o.update(sm.RemoteSvc('charUnboundMgr').GetCharNewExtraCreationInfo())
                    self.charCreationInfo = o
            finally:
                uthread.UnLock(self)

        return self.charCreationInfo

    @telemetry.ZONE_METHOD
    def GetData(self, attribute, keyVal = None, shuffle = 0):
        ccinfo = self.GetCharCreationInfo()
        if attribute in ('bloodlines', 'ancestries', 'schools') and hasattr(ccinfo, attribute):
            retval = getattr(ccinfo, attribute)
            if keyVal:
                try:
                    retval = [ each for each in retval if getattr(each, keyVal[0]) == keyVal[1] ]
                except:
                    retval = []

            if shuffle:
                retval = copy.copy(retval)
                random.shuffle(retval)
            if len(retval) == 1:
                return retval[0]
            elif len(retval) == 0:
                return None
            else:
                return retval
        else:
            return None

    def GoBack(self, *args):
        sm.GetService('viewState').ActivateView('charsel')

    def GoCharacterCreation(self, charID, gender, bloodlineID, dollState = None):
        uicore.layer.charactercreation.SetCharDetails(charID, gender, bloodlineID, dollState=dollState)

    def CreateCharacterWithDoll(self, charactername, bloodlineID, genderID, ancestryID, charInfo, portraitInfo, schoolID, *args):
        self.LogInfo('charInfo:', charInfo)
        charID = sm.RemoteSvc('charUnboundMgr').CreateCharacterWithDoll(charactername, bloodlineID, genderID, ancestryID, charInfo, portraitInfo, schoolID)
        return charID

    def UpdateExistingCharacterFull(self, charID, dollInfo, portraitInfo, dollExists):
        sm.RemoteSvc('paperDollServer').UpdateExistingCharacterFull(charID, dollInfo, portraitInfo, dollExists)
        sm.GetService('paperdoll').ClearCurrentPaperDollData()

    def UpdateExistingCharacterLimited(self, charID, dollInfo, portraitInfo, dollExists):
        dollData = dollInfo.copy()
        dollData.sculpts = []
        self.LogInfo('UpdateExistingCharacterLimited', charID)
        sm.RemoteSvc('paperDollServer').UpdateExistingCharacterLimited(charID, dollData, portraitInfo, dollExists)
        sm.GetService('paperdoll').ClearCurrentPaperDollData()

    def UpdateExistingCharacterBloodline(self, charID, dollInfo, portraitInfo, dollExists, bloodlineID):
        sm.GetService('paperdoll').ClearCurrentPaperDollData()

    @telemetry.ZONE_METHOD
    def GetPortraitData(self, charID):
        data = sm.RemoteSvc('paperDollServer').GetPaperDollPortraitDataFor(charID)
        if len(data):
            return data[0]

    @telemetry.ZONE_METHOD
    def GetRaceData(self, shuffle = 0, shuffleFirstTime = 0):
        if self.raceData is None:
            self.PrepareRaceData()
            if shuffleFirstTime:
                shuffle = 1
        if shuffle == 0:
            return self.raceData
        retval = copy.deepcopy(self.raceData)
        random.shuffle(retval)
        if shuffleFirstTime:
            self.raceData = retval
        return retval

    @telemetry.ZONE_METHOD
    def GetRaceDataByID(self, raceID = None):
        if self.raceDataByID is None:
            self.PrepareRaceData()
        if raceID is None:
            return self.raceDataByID
        return self.raceDataByID[raceID]

    @telemetry.ZONE_METHOD
    def GetBloodlineDataByRaceID(self, *args):
        if self.bloodlineDataByRaceID is None:
            self.bloodlineDataByRaceID, self.bloodlineDataByID = self.PrepareBloodlineData()
        return self.bloodlineDataByRaceID

    @telemetry.ZONE_METHOD
    def GetBloodlineDataByID(self, *args):
        if self.bloodlineDataByID is None:
            self.bloodlineDataByRaceID, self.bloodlineDataByID = self.PrepareBloodlineData()
        return self.bloodlineDataByID

    @telemetry.ZONE_METHOD
    def PrepareRaceData(self, *args):
        raceDict = {}
        raceList = []
        for each in cfg.races:
            if each.raceID in [const.raceCaldari,
             const.raceMinmatar,
             const.raceGallente,
             const.raceAmarr]:
                raceDict[each.raceID] = each
                raceList.append(each)

        self.raceData, self.raceDataByID = raceList, raceDict

    @telemetry.ZONE_METHOD
    def PrepareBloodlineData(self, *args):
        bloodlinesByRaceID = {}
        bloodlinesByID = {}
        for raceID in [const.raceCaldari,
         const.raceMinmatar,
         const.raceGallente,
         const.raceAmarr]:
            bloodlines = []
            for each in self.GetData('bloodlines', shuffle=1):
                if each.raceID == raceID:
                    bloodlines.append(each)
                    bloodlinesByID[each.bloodlineID] = each

            bloodlinesByRaceID[raceID] = bloodlines

        return (bloodlinesByRaceID, bloodlinesByID)

    def StoreCurrentDollState(self, state, *args):
        self.dollState = state

    def NoExistingCustomization(self, *arags):
        return self.dollState == const.paperdollStateNoExistingCustomization

    def ClearMyAvailabelTypeIDs(self, *args):
        self.availableTypeIDs = None

    def GetMyApparel(self):
        if getattr(self, 'availableTypeIDs', None) is not None:
            return self.availableTypeIDs
        availableTypeIDs = set()
        if session.stationid2:
            try:
                inv = self.invCache.GetInventory(const.containerHangar)
                availableTypeIDs.update({i.typeID for i in inv.List() if i.categoryID == const.categoryApparel})
                inv = self.invCache.GetInventoryFromId(session.charid)
                availableTypeIDs.update({i.typeID for i in inv.List() if i.flagID == const.flagWardrobe})
            except Exception as e:
                log.LogException()

        self.availableTypeIDs = availableTypeIDs
        return self.availableTypeIDs