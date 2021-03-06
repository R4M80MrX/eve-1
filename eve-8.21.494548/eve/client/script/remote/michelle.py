#Embedded file name: c:/depot/games/branches/release/EVE-TRANQUILITY/eve/client/script/remote/michelle.py
import sys
import log
import stackless
import math
import uthread
import destiny
import blue
import util
import decometaclass
import moniker
import service
import foo
import collections
globals().update(service.consts)
import telemetry

class Michelle(service.Service):
    __guid__ = 'svc.michelle'
    __exportedcalls__ = {'AddBallpark': [ROLE_ANY],
     'RemoveBallpark': [ROLE_ANY],
     'GetBallpark': [ROLE_ANY],
     'GetRemotePark': [ROLE_ANY],
     'GetBallparkForScene': [ROLE_ANY],
     'GetBall': [ROLE_ANY],
     'GetItem': [ROLE_ANY],
     'GetDroneState': [ROLE_ANY],
     'GetDrones': [ROLE_ANY],
     'Refresh': [ROLE_ANY],
     'GetCharIDFromShipID': [ROLE_ANY],
     'GetFleetState': [ROLE_ANY]}
    __notifyevents__ = ['DoDestinyUpdate',
     'DoDestinyUpdates',
     'OnFleetStateChange',
     'OnDroneStateChange',
     'OnDroneActivityChange',
     'OnAudioActivated',
     'DoSimClockRebase',
     'OnSessionChanged']
    __dependencies__ = ['machoNet', 'dataconfig', 'crimewatchSvc']

    def Run(self, ms):
        self.state = SERVICE_START_PENDING
        self.__bp = None
        self.bpReady = False
        self.quit = 0
        self.scenes = {}
        self.ballNotInParkErrors = {}
        self.handledBallErrors = set()
        self.ballQueue = uthread.Queue()
        uthread.pool('michelle:ballDispatcher', self.Dispatcher)
        if self.logChannel.IsOpen(1):
            self.logInfo = True
        else:
            self.logInfo = False
        self.state = SERVICE_RUNNING

    def OnSessionChanged(self, isRemote, session, change):
        if 'locationid' in change:
            oldLocation, newLocation = change['locationid']
            if util.IsSolarSystem(oldLocation):
                self.RemoveBallpark()
                self.LogInfo('Removed ballpark for', oldLocation)
            if util.IsSolarSystem(newLocation):
                sm.GetService('space')
                self.LogInfo('Adding new ballpark for', newLocation)
                self.AddBallpark(newLocation)

    def OnFleetStateChange(self, fleetState):
        if self.__bp is not None:
            self.__bp.OnFleetStateChange(fleetState)

    def OnDroneStateChange(self, droneID, ownerID, controllerID, activityState, droneTypeID, controllerOwnerID, targetID):
        if self.__bp is not None:
            self.__bp.OnDroneStateChange(droneID, ownerID, controllerID, activityState, droneTypeID, controllerOwnerID, targetID)

    def OnDroneActivityChange(self, droneID, activityID, activity):
        if self.__bp is not None:
            self.__bp.OnDroneActivityChange(droneID, activityID, activity)

    def GetFleetState(self):
        if self.__bp is None:
            return
        if session.fleetid is None:
            return
        if self.__bp.fleetState is None:
            self.__bp.fleetState = self.GetRemotePark().GetFleetState()
        return self.__bp.fleetState

    def Refresh(self):
        if self.__bp is not None:
            self.__bp.Refresh()

    def Stop(self, ms):
        if self.__bp is not None:
            self.__bp.Release()
            self.__bp = None
        self.ballQueue.non_blocking_put(None)
        self.quit = 1

    def AddBallpark(self, solarsystemID):
        self.LogNotice('Adding ballpark', solarsystemID)
        self.bpReady = False
        if self.__bp is not None:
            self.__bp.Release()
        self.__bp = blue.classes.CreateInstance('destiny.Ballpark')
        self.LogInfo('GetBallpark1 object', self.__bp, 'now has:', sys.getrefcount(self.__bp), 'references')
        Park(self.__bp, {'broker': self,
         'solarsystemID': long(solarsystemID),
         'hideDesyncSymptoms': True})
        self.LogInfo('GetBallpark2 object', self.__bp, 'now has:', sys.getrefcount(self.__bp), 'references')
        formations = sm.RemoteSvc('beyonce').GetFormations()
        self.__bp.LoadFormations(formations)
        self.ballNotInParkErrors = {}
        self.handledBallErrors = set()
        self.__bp.SetBallNotInParkCallback(self.HandleBallNotInParkError)
        sm.ScatterEvent('OnAddBallpark')
        self.__bp.Start()
        self.bpReady = True
        self.LogNotice('Done adding ballpark', solarsystemID)
        return self.__bp

    def RemoveBallpark(self):
        if self.__bp is not None:
            self.__bp.Release()
            self.__bp = None

    def GetBallpark(self, doWait = False):
        if self.bpReady:
            return self.__bp
        elif not doWait:
            return None
        WAIT_TIME = 1
        MAX_TRIES = 30
        tries = 0
        while not self.bpReady and tries < MAX_TRIES:
            self.LogInfo('Waiting for ballpark', tries)
            tries = tries + 1
            blue.pyos.synchro.SleepSim(WAIT_TIME * 1000)

        if not self.bpReady:
            logstring = 'Failed to get a valid ballpark in time after trying %d times' % tries
            self.LogError(logstring)
            if session.charid:
                uthread.new(sm.ProxySvc('clientStatLogger').LogString, logstring)
            return None
        else:
            return self.__bp

    def GetRemotePark(self):
        if self.__bp is None:
            return
        return self.__bp.remoteBallpark

    def GetBallparkForScene(self, scene):
        self.LogInfo('GetBallpark object', self.__bp, 'now has:', sys.getrefcount(self.__bp), 'references')
        if not self.__bp:
            return None
        if self.__bp not in self.scenes:
            self.scenes[self.__bp] = []
        self.scenes[self.__bp].append(scene)
        return self.__bp

    def GetBall(self, id):
        if self.__bp is not None:
            return self.__bp.GetBall(id)
        else:
            return

    def GetItem(self, id):
        if self.__bp is not None:
            return self.__bp.GetInvItem(id)

    def GetDroneState(self, droneID):
        if self.__bp is not None:
            return self.__bp.stateByDroneID.get(droneID, None)

    def GetDroneActivity(self, droneID):
        if self.__bp is not None:
            return self.__bp.activityByDrone.get(droneID, None)

    def GetDrones(self):
        if self.__bp is not None:
            return self.__bp.stateByDroneID

    def DoDestinyUpdate(self, state, waitForBubble, dogmaMessages = [], doDump = True):
        self.LogInfo('DoDestinyUpdate call for tick', state[0][0], 'containing', len(state), 'updates.  waitForBubble=', waitForBubble)
        if self.__bp is None:
            raise RuntimeError('No ballpark for update')
        if dogmaMessages:
            self.LogInfo('OnMultiEvent has', len(dogmaMessages), 'messages')
            sm.ScatterEvent('OnMultiEvent', dogmaMessages)
        expandedStates = []
        for action in state:
            if action[1][0] == 'PackagedAction':
                try:
                    unpackagedActions = blue.marshal.Load(action[1][1])
                    expandedStates.extend(unpackagedActions)
                except:
                    log.LogException('Exception whilst expanding a PackagedAction')
                    sys.exc_clear()

            else:
                expandedStates.append(action)

        state = expandedStates
        timestamps = set()
        for action in state:
            timestamps.add(action[0])

        if len(timestamps) > 1:
            self.LogError('Found update batch with', len(state), 'items and', len(timestamps), 'timestamps')
            for action in state:
                self.LogError('Action:', action)

            sm.GetService('clientStatsSvc').OnFatalDesync()
            if not self.__bp.hideDesyncSymptoms:
                uthread.new(eve.Message, 'CustomInfo', {'info': 'Desync mismatched updates problem occurred'})
        self.__bp.FlushState(state, waitForBubble, doDump)

    def DoDestinyUpdates(self, updates):
        self.LogInfo('DoDestinyUpdates call, count=', len(updates))
        localDump = False
        idx = 0
        for args in updates:
            idx += 1
            self.LogInfo('DoDestinyUpdate(s)', idx, '/', len(updates))
            if len(args) == 2:
                state, waitForBubble = args
                self.DoDestinyUpdate(state, waitForBubble, doDump=not localDump)
            else:
                state, waitForBubble, dogmaMessages = args
                self.DoDestinyUpdate(state, waitForBubble, dogmaMessages, doDump=not localDump)

        if self.logInfo and localDump:
            self.__bp.DumpHistory()

    def GetCharIDFromShipID(self, shipID):
        if self.__bp is None:
            return
        if shipID not in self.__bp.slimItems:
            return
        slimItem = self.__bp.slimItems[shipID]
        return slimItem.charID

    def GetRelativity(self):
        import blue
        import util
        import math
        lpark = self.GetBallpark()
        ball = self.GetBall(eve.session.shipid)
        presTime = lpark.currentTime
        pretTime = blue.os.GetWallclockTime()
        prerTime = blue.os.GetWallclockTimeNow()
        preX = ball.x
        preY = ball.y
        preZ = ball.z
        diff, x, y, z, sTime, tTime, rTime = self.GetRemotePark().GetRelativity(preX, preY, preZ, presTime, pretTime, prerTime)
        ldiff = math.sqrt((preX - x) ** 2 + (preY - y) ** 2 + (preZ - z) ** 2)
        postsTime = lpark.currentTime
        posttTime = blue.os.GetWallclockTime()
        postrTime = blue.os.GetWallclockTimeNow()
        pdiff = math.sqrt((ball.x - x) ** 2 + (ball.y - y) ** 2 + (ball.z - z) ** 2)
        print '------------------------------------------------------------------------------------'
        print 'Ticks: client(%s) to server(%s) = %s, server(%s) to client(%s) = %s' % (presTime,
         sTime,
         sTime - presTime,
         sTime,
         postsTime,
         postsTime - sTime)
        print 'Time: client to server %s, server to client %s. Total time to handle call %s' % (util.FmtSec(rTime - prerTime), util.FmtSec(postrTime - rTime), util.FmtSec(postrTime - prerTime))
        print 'pre diff %s on server %s, post diff %s' % (ldiff, diff, pdiff)
        if sTime - postsTime > 0:
            print 'We are behind the server, lets catch up'
            last = lpark.currentTime
            while sTime - lpark.currentTime >= 0:
                if last != lpark.currentTime:
                    last = lpark.currentTime
                    print 'pos diff at step %s is %s' % (lpark.currentTime, math.sqrt((ball.x - x) ** 2 + (ball.y - y) ** 2 + (ball.z - z) ** 2))
                blue.pyos.synchro.Yield()

        elif sTime - postsTime == 0:
            print 'client and server match, as the client should be ahead there is some lag'
        else:
            print 'We are ahead of the server (at least when the call had come back), to handle this case we need the pos history for the last 10 ticks or so'

    def Dispatcher(self):
        while self.state in (SERVICE_RUNNING, SERVICE_START_PENDING):
            try:
                orders = None
                orders = self.ballQueue.get()
                if orders is None:
                    return
                self.ProcessDispatchOrders(orders)
            except StandardError:
                self.LogError('In michelle.Dispatcher')
                log.LogException()
                sys.exc_clear()

    def ProcessDispatchOrders(self, orders):
        ownersToPrime, tickersToPrime, allyTickersToPrime, stuffToAdd, newState, locationsToPrime = orders
        if locationsToPrime:
            try:
                cfg.evelocations.Prime(locationsToPrime)
            except StandardError:
                self.LogError('In michelle.Dispatcher')
                log.LogException()
                sys.exc_clear()

        if ownersToPrime:
            try:
                cfg.eveowners.Prime(ownersToPrime)
            except StandardError:
                self.LogError('In michelle.Dispatcher')
                log.LogException()
                sys.exc_clear()

        if tickersToPrime:
            try:
                cfg.corptickernames.Prime(tickersToPrime)
            except StandardError:
                self.LogError('In michelle.Dispatcher')
                log.LogException()
                sys.exc_clear()

        if allyTickersToPrime:
            try:
                cfg.allianceshortnames.Prime(allyTickersToPrime)
            except StandardError:
                self.LogError('In michelle.Dispatcher')
                log.LogException()
                sys.exc_clear()

        realBalls = {}
        for ballID, slimItem in stuffToAdd:
            try:
                if self.__bp and ballID in self.__bp.balls:
                    ball = self.__bp.balls[ballID]
                    if not self.__bp.slimItems.has_key(ballID):
                        realBalls[ballID] = (ball, slimItem)
                    self.__bp.slimItems[ballID] = slimItem
            except StandardError:
                self.LogError('In michelle.Dispatcher')
                log.LogException()
                sys.exc_clear()

        if len(realBalls):
            t = stackless.getcurrent()
            timer = t.PushTimer(blue.pyos.taskletTimer.GetCurrent() + '::DoBallsAdded')
            sm.SendEvent('DoBallsAdded', realBalls.values())
            t.PopTimer(timer)
        if newState is not None:
            t = stackless.getcurrent()
            timer = t.PushTimer(blue.pyos.taskletTimer.GetCurrent() + '::OnNewState')
            sm.ScatterEvent('OnNewState', newState)
            t.PopTimer(timer)

    def HandleBallNotInParkError(self, ball):
        now = blue.os.GetWallclockTime()
        ballID = ball.id
        if ballID in self.ballNotInParkErrors and ballID not in self.handledBallErrors:
            diff = now - self.ballNotInParkErrors[ballID]
            if 5 * SEC < diff:
                if not self.logChannel.IsOpen(4):
                    print 'Ball', ballID, 'not in park!'
                else:
                    self.LogError('-----------------------------------------------------------------------------------')
                    self.LogError('BALL NOT IN PARK:', ballID)
                    self.LogError('-----------------------------------------------------------------------------------')
                    self.LogError('Ball has not been in park for', diff / SEC, 'seconds.')
                    self.LogError("Probable cause is trinity graphics that haven't been cleaned up.")
                    self.LogError('Ball Info:')
                    self.LogError('\tBall deco type:', getattr(ball, '__class__', '?'))
                    self.LogError('\tModel:', getattr(ball, 'model', None))
                    self.LogError('\tExploded:', getattr(ball, 'exploded', '?'))
                    if ball.ballpark is None:
                        self.LogError('\tNot in any ballpark')
                    else:
                        self.LogError('\tIn Ballpark:', getattr(ball.ballpark, 'solarsystemID', '?'))
                    slimItem = self.GetItem(ball.id)
                    if slimItem:
                        self.LogError('Slim Item Info:')
                        self.LogError('\tType:', slimItem.typeID)
                    self.LogError('Checking Scene')
                    scene = sm.GetService('sceneManager').GetActiveScene()
                    if scene is not None:
                        for obj in scene.objects:
                            if len([ foundBall for foundBall in obj.Find('destiny.ClientBall') if foundBall == ball ]):
                                if hasattr(obj, 'display'):
                                    obj.display = 0
                                if hasattr(obj, 'update'):
                                    obj.update = 0
                                self.LogError('\tAttached to', obj.__bluetype__, 'named', getattr(obj, 'name', '?'), ' in Scene')

                self.handledBallErrors.add(ballID)
                del self.ballNotInParkErrors[ballID]
        else:
            self.ballNotInParkErrors[ballID] = now

    def OnAudioActivated(self):
        if self.__bp is not None:
            self.__bp.OnAudioActivated()

    def DoSimClockRebase(self, times):
        oldSimTime, newSimTime = times
        if self.__bp:
            self.__bp.AdjustTimes(newSimTime - oldSimTime)


SEC = 10000000L
MIN = SEC * 60L
HOUR = MIN * 60L

class Park(decometaclass.WrapBlueClass('destiny.Ballpark')):
    __guid__ = 'michelle.Park'
    __nonpersistvars__ = ['states',
     'broker',
     'lastStamp',
     'dirty',
     'remoteBallpark',
     'slimItems',
     'damageState',
     'solItem',
     'validState',
     'history']
    __persistdeco__ = 0
    __categoryRequireOwnerPrime__ = None
    __predefs__ = 0

    def __init__(self):
        if not self.__predefs__:
            self.__predefs__ = 1
            self.__categoryRequireOwnerPrime__ = (const.categoryShip, const.categoryDrone)
        self.tickInterval = const.simulationTimeStep
        self.lastStamp = -1
        self.dirty = 0
        self.states = []
        self.slimItems = {}
        self.damageState = {}
        self.stateByDroneID = {}
        self.fleetState = None
        self.solItem = None
        self.validState = 0
        self.history = []
        self.latestSetStateTime = 0
        self.shouldRebase = False
        self.activityByDrone = {}
        self.clientBallNextID = -8000000000000000000L
        self.remoteBallpark = moniker.GetBallPark(self.solarsystemID)
        self.remoteBallpark.Bind()
        self.scatterEvents = {'Orbit': 1,
         'GotoDirection': 1,
         'WarpTo': 1,
         'SetBallRadius': 1,
         'GotoPoint': 1,
         'SetBallInteractive': 1,
         'SetBallFree': 1,
         'SetBallHarmonic': 1,
         'FollowBall': 1}
        self.nonDestinyCriticalFunctions = set(['OnDamageStateChange',
         'OnSpecialFX',
         'OnFleetDamageStateChange',
         'OnShipStateUpdate',
         'OnSlimItemChange',
         'OnDroneStateChange',
         'OnSovereigntyChanged'])

    def __del__(self):
        self.remoteBallpark = None
        self.broker = None
        self.states = []

    def RequestReset(self):
        self.validState = False
        if self.hideDesyncSymptoms:
            self.FlushSimulationHistory(newBaseSnapshot=False)
        else:
            self.RebaseStates(1)
        uthread.pool('michelle::UpdateStateRequest', self.remoteBallpark.UpdateStateRequest)

    def DoPostTick(self, stamp):
        if self.shouldRebase:
            if self.hideDesyncSymptoms:
                self.FlushSimulationHistory()
            else:
                self.RebaseStates()
            self.shouldRebase = False
        elif stamp > self.lastStamp + 10:
            self.StoreState()

    def DumpHistory(self):
        self.broker.LogInfo('------ History Dump', self.currentTime, '-------')
        rev = self.history[:]
        rev.reverse()
        for state, waitForBubble in rev:
            self.broker.LogInfo('state waiting:', ['no', 'yes'][waitForBubble])
            lastState = None
            lastStateCount = 0
            for entry in state:
                eventStamp, event = entry
                funcName, args = event
                nextState = ['[',
                 eventStamp,
                 ']',
                 funcName]
                if nextState != lastState:
                    if lastState is not None:
                        if lastStateCount != 1:
                            lastState.append('(x %d)' % lastStateCount)
                        self.broker.LogInfo(*lastState)
                    lastState = nextState
                    lastStateCount = 1
                else:
                    lastStateCount += 1

            if lastState is not None:
                if lastStateCount != 1:
                    lastState.append('(x %d)' % lastStateCount)
                self.broker.LogInfo(*lastState)
            self.broker.LogInfo(' ')

    def DoPreTick(self, stamp):
        if not self.hideDesyncSymptoms:
            while len(self.history) > 0:
                state, waitForBubble = self.history[0]
                if waitForBubble:
                    return
                eventStamp, event = state[0]
                if eventStamp > self.currentTime and eventStamp - self.currentTime < 3:
                    break
                funcName, args = event
                self.RealFlushState(state)
                del self.history[0]
                if len(self.history) > 1:
                    if self.history[0][1]:
                        return
                    self._parent_Evolve()

            return
        while len(self.history) > 0:
            state, waitForBubble = self.history[0]
            if waitForBubble:
                return
            eventStamp = state[0][0]
            if eventStamp > self.currentTime and eventStamp - self.currentTime < 3:
                break
            self.RealFlushState(state)
            del self.history[0]
            if self.validState and self.shouldRebase:
                self.StoreState(midTick=True)
            if len(self.history) > 1:
                if self.history[0][1]:
                    return
                self._parent_Evolve()

    def StoreState(self, midTick = False):
        if self.dirty or not self.isRunning:
            return
        ms = blue.MemStream()
        self.WriteFullStateToStream(ms)
        if self.hideDesyncSymptoms:
            self.states.append([ms, self.currentTime, midTick])
        else:
            self.states.append([ms, self.currentTime])
        if self.broker.logInfo:
            self.broker.LogInfo('StoreState:', self.currentTime, 'midTick:', midTick)
        if len(self.states) > 10:
            self.states = self.states[:1] + self.states[3:3] + self.states[-5:]
        self.lastStamp = self.currentTime

    def Release(self):
        sm.ScatterEvent('OnReleaseBallpark')
        self._parent_Pause()
        egoID = self.ego
        for ballID in self.balls.keys():
            if ballID == egoID or ballID < 0:
                continue
            self.RemoveBall(ballID)

        if egoID is not None:
            self.RemoveBall(egoID)
        self._parent_ClearAll()
        if self.hideDesyncSymptoms:
            self.FlushSimulationHistory(newBaseSnapshot=False)
        else:
            self.RebaseStates(1)
        if self in self.broker.scenes:
            for scene in self.broker.scenes[self]:
                if scene and hasattr(scene, 'ballpark'):
                    scene.ballpark = None

            del self.broker.scenes[self]
        self.validState = False
        self.solItem = None
        self.remoteBallpark = None
        self.slimItems = {}
        self.damageState = {}
        self.history = []
        self.latestSetStateTime = 0
        self.broker.LogWarn('Ballpark object has:', sys.getrefcount(self), 'references left')

    def SetState(self, bag):
        self.stateByDroneID = bag.droneState.Index('droneID')
        sm.SendEvent('DoBallClear', bag.solItem)
        self.ClearAll()
        ms = blue.MemStream()
        ms.Write(bag.state)
        self._parent_ReadFullStateFromStream(ms)
        self.ego = long(bag.ego)
        self._parent_Start()
        self.slimItems = {}
        stuffToAdd = []
        ownersToPrime = []
        tickersToPrime = []
        allyTickersToPrime = []
        locationsToPrime = []
        for slimItem in bag.slims:
            if type(slimItem) is int:
                raise TypeError
            if slimItem.itemID not in self.balls:
                raise RuntimeError('BallNotInPark', slimItem.itemID, slimItem)
            ball = self.balls[slimItem.itemID]
            if ball.id > destiny.DSTLOCALBALLS:
                stuffToAdd.append((ball.id, slimItem))
                if slimItem.categoryID in self.__categoryRequireOwnerPrime__:
                    ownersToPrime.append(slimItem.ownerID)
                    ownersToPrime.append(slimItem.corpID)
                if slimItem.corpID and slimItem.corpID not in tickersToPrime:
                    tickersToPrime.append(slimItem.corpID)
                if slimItem.allianceID and slimItem.allianceID not in allyTickersToPrime:
                    allyTickersToPrime.append(slimItem.allianceID)
                if util.IsCelestial(slimItem.itemID) or util.IsStargate(slimItem.itemID):
                    locationsToPrime.append(slimItem.itemID)
                elif slimItem.itemID >= const.minFakeItem and slimItem.nameID is not None:
                    cfg.evelocations.Hint(slimItem.itemID, [slimItem.itemID,
                     '',
                     ball.x,
                     ball.y,
                     ball.z,
                     slimItem.nameID])
                elif not (slimItem.categoryID == const.categoryAsteroid or slimItem.groupID == const.groupHarvestableCloud):
                    cfg.evelocations.Hint(slimItem.itemID, [slimItem.itemID,
                     slimItem.name,
                     ball.x,
                     ball.y,
                     ball.z,
                     slimItem.nameID])

        self.validState = True
        if self.hideDesyncSymptoms:
            self.FlushSimulationHistory()
        else:
            self.RebaseStates()
        self.broker.ballQueue.non_blocking_put((ownersToPrime,
         tickersToPrime,
         allyTickersToPrime,
         stuffToAdd,
         self,
         locationsToPrime))
        now = blue.os.GetSimTime()
        self.damageState = {}
        for k, v in bag.damageState.iteritems():
            self.damageState[k] = (v, now)

        for effectInfo in bag.effectStates:
            self.OnSpecialFX(*effectInfo)
            self.ScatterEwars(*effectInfo)

        sm.services['pwn'].ProcessAllianceBridgeModePurge()
        for shipID, toSolarsystemID, toBeaconID in bag.allianceBridges:
            sm.services['pwn'].OnAllianceBridgeModeChange(shipID, toSolarsystemID, toBeaconID, True)

        self.solItem = bag.solItem

    def GetDamageState(self, itemID):
        if itemID not in self.damageState:
            return
        mainctx = blue.pyos.taskletTimer.EnterTasklet('Michelle::GetDamageState')
        try:
            state, time = self.damageState[itemID]
            if not state:
                return
            ret = []
            if type(state[0]) in (list, tuple):
                now = blue.os.GetSimTime()
                num, tau = state[0][:2]
                sq = math.sqrt(num)
                exp = math.exp((time - now) / const.dgmTauConstant / tau)
                ret.append((1.0 + (sq - 1.0) * exp) ** 2)
            else:
                ret.append(None)
            ret = ret + list(state[-2:])
        finally:
            blue.pyos.taskletTimer.ReturnFromTasklet(mainctx)

        return ret

    def DistanceBetween(self, srcID, dstID):
        dist = self.GetSurfaceDist(srcID, dstID)
        if dist is None:
            raise RuntimeError('DistanceBetween:: invalid balls', srcID, dstID)
        if dist < 0.0:
            dist = 0.0
        return dist

    def RebaseStates(self, wipe = 0):
        if self.broker.logInfo:
            self.broker.LogInfo('State history rebased at', self.currentTime)
        self.states = []
        if not wipe:
            self.StoreState()

    def FlushSimulationHistory(self, newBaseSnapshot = True):
        if self.broker.logInfo:
            self.broker.LogInfo('State history rebased at', self.currentTime, 'newBaseSnapshot', newBaseSnapshot)
        lastMidState = None
        if newBaseSnapshot and len(self.states):
            lastMidState = self.states[-1]
            if not lastMidState[2] or lastMidState[1] != self.currentTime - 1:
                lastMidState = None
        self.states = []
        if newBaseSnapshot:
            if lastMidState:
                self.states.append(lastMidState)
            self.StoreState()
            for item in self.states:
                if self.broker.logInfo:
                    self.broker.LogInfo('State entry', item)

    def SynchroniseToSimulationTime(self, stamp):
        if self.broker.logInfo:
            self.broker.LogInfo('SynchroniseToSimulationTime looking for:', stamp, '- current:', self.currentTime)
        if stamp < self.currentTime:
            lastStamp = 0
            lastState = None
            for item in self.states:
                if item[1] <= stamp:
                    lastStamp = item[1]
                    lastState = item[0]
                else:
                    continue

            if not lastState:
                self.broker.LogWarn('SynchroniseToSimulationTime: Did not find any state')
                return 0
            self._parent_ReadFullStateFromStream(lastState, 1)
        else:
            lastStamp = self.currentTime
        for i in range(stamp - lastStamp):
            self._parent_Evolve()

        if self.broker.logInfo:
            self.broker.LogInfo('SynchroniseToSimulationTime found:', self.currentTime)
        return 1

    def FlushState(self, state, waitForBubble, doDump = True):
        self.broker.LogInfo('Server Update with', len(state), 'event(s) added to history')
        if len(state) == 0:
            self.broker.LogWarn('Empty state received from remote ballpark')
            return
        if state[0][1][0] == 'SetState':
            self.latestSetStateTime = state[0][0]
            self.broker.LogInfo('Michelle received a SetState at time', self.latestSetStateTime, '. Clearing out-of-date entries...')
            self.history[:] = [ historyEntry for historyEntry in self.history if historyEntry[0][0][0] >= self.latestSetStateTime ]
            if self.broker.logInfo and doDump:
                self.DumpHistory()
        else:
            entryTime = state[0][0]
            if entryTime < self.latestSetStateTime:
                self.broker.LogWarn('Michelle discarded a state that was too old', entryTime, ' < ', self.latestSetStateTime)
                if self.broker.logInfo and doDump:
                    self.DumpHistory()
                return
        if not hasattr(self, 'hideDesyncSymptoms'):
            sm.services['michelle'].LogError('UNABLE TO FIND ATTRIBUTE ON BALLPARK, RELEASED?', getattr(self, 'broker', 'NO BROKER'), getattr(self, 'solarSystemID', 'NO SOLAR SYSTEM ID'))
            return
        if not self.hideDesyncSymptoms:
            if len(self.history) and self.history[-1][0][0][0] == state[0][0]:
                if self.broker.logInfo:
                    self.broker.LogInfo('FlushState: Coalescing states')
                self.history[-1][0].extend(state)
                self.history[-1][1] = False
            else:
                self.history.append([state, waitForBubble])
            if self.broker.logInfo and doDump:
                self.DumpHistory()
            return
        oldStatesByTime = {}
        newestOldStateTime = 0
        for oldState in self.history:
            oldStatesByTime[oldState[0][0][0]] = oldState

        if len(self.history):
            newestOldStateTime = self.history[-1][0][0][0]
        entriesByTime = {}
        for entry in state:
            entryTime = entry[0]
            if not entriesByTime.has_key(entryTime):
                entriesByTime[entryTime] = [entry]
            else:
                entriesByTime[entryTime].append(entry)

        timeList = entriesByTime.keys()
        timeList.sort()
        for entryTime in timeList:
            if entryTime in oldStatesByTime:
                if self.broker.logInfo:
                    self.broker.LogInfo('FlushState: Incorporating events into existing tick', entryTime)
                oldStatesByTime[entryTime][0].extend(entriesByTime[entryTime])
                oldStatesByTime[entryTime][1] = False
            elif entryTime > newestOldStateTime:
                if self.broker.logInfo:
                    self.broker.LogInfo('FlushState: Adding update for new tick', entryTime)
                self.history.append([entriesByTime[entryTime], waitForBubble])
                waitForBubble = False
            else:
                for i in range(len(self.history)):
                    if self.history[i][0][0][0] > entryTime:
                        if self.broker.logInfo:
                            self.broker.LogInfo('FlushState: Injecting update for previous tick', entryTime)
                        self.history.insert(i, [entriesByTime[entryTime], waitForBubble])
                        waitForBubble = False
                        break

        if self.broker.logInfo and doDump:
            self.DumpHistory()

    def RealFlushState(self, state):
        if self.broker.logInfo:
            self.broker.LogInfo('Handling Server Update with', len(state), 'event(s)')
        if len(state) == 0:
            self.broker.LogWarn('Empty state received from remote ballpark')
            return
        entryStamp = self.currentTime
        eventStamp, event = state[0]
        funcName, args = event
        if funcName == 'SetState':
            if self.broker.logInfo and util.IsFullLogging():
                self.broker.LogInfo('Action: %12.12s' % funcName, eventStamp, '- current:', self.currentTime, args)
            apply(self.SetState, args)
        if self.validState:
            self.shouldRebase = False
            synchronised = False
            for action in state:
                eventStamp, event = action
                funcName, args = event
                if funcName == 'SetState':
                    continue
                if funcName == 'Challenge':
                    self.broker.LogWarn(eventStamp, '->', args)
                    continue
                if self.broker.logInfo and util.IsFullLogging():
                    self.broker.LogInfo('Action: %12.12s' % funcName, eventStamp, '- current:', self.currentTime, args)
                if funcName in self.nonDestinyCriticalFunctions:
                    apply(getattr(self, funcName), args)
                else:
                    if not synchronised:
                        synchronised = self.SynchroniseToSimulationTime(eventStamp)
                    if not synchronised:
                        sm.GetService('clientStatsSvc').OnRecoverableDesync()
                        self.broker.LogWarn('Failed to synchronize to', eventStamp, 'Requesting new state')
                        self.RequestReset()
                        return
                    self.shouldRebase = True
                    try:
                        if funcName in ('AddBalls', 'AddBalls2', 'RemoveBalls', 'SetState', 'RemoveBall', 'TerminalExplosion'):
                            if funcName == 'RemoveBalls':
                                exploders = [ x[1][1][0] for x in state if x[1][0] == 'TerminalExplosion' ]
                                args = args + (exploders,)
                            apply(getattr(self, funcName), args)
                        else:
                            apply(getattr(self, '_parent_' + funcName), args)
                            if funcName in self.scatterEvents:
                                sm.ScatterEvent('OnBallparkCall', funcName, args)
                    except Exception as e:
                        log.LogException('Something potentially bad happened with %s' % funcName)
                        sys.exc_clear()
                        continue

        else:
            self.broker.LogInfo('Events ignored')

    def TerminalExplosion(self, shipID, bubbleID = None, ballIsGlobal = False):
        pass

    def AddBalls(self, chunk):
        state, slims, damageDict = chunk
        ms = blue.MemStream()
        ms.Write(state)
        self._parent_ReadFullStateFromStream(ms, 2)
        stuffToAdd = []
        ownersToPrime = []
        tickersToPrime = []
        allyTickersToPrime = []
        locationsToPrime = []
        for slimItem in slims:
            if type(slimItem) is int:
                raise TypeError
            if slimItem.itemID in self.slimItems:
                continue
            ball = self.balls[slimItem.itemID]
            if slimItem.itemID > destiny.DSTLOCALBALLS:
                stuffToAdd.append((slimItem.itemID, slimItem))
                if slimItem.categoryID in self.__categoryRequireOwnerPrime__:
                    ownersToPrime.append(slimItem.ownerID)
                    if slimItem.charID is not None:
                        ownersToPrime.append(slimItem.charID)
                        ownersToPrime.append(slimItem.corpID)
                if slimItem.corpID and slimItem.corpID not in tickersToPrime:
                    tickersToPrime.append(slimItem.corpID)
                if slimItem.allianceID and slimItem.allianceID not in allyTickersToPrime:
                    allyTickersToPrime.append(slimItem.allianceID)
                if util.IsCelestial(slimItem.itemID) or util.IsStargate(slimItem.itemID):
                    locationsToPrime.append(slimItem.itemID)
                elif slimItem.itemID >= const.minFakeItem and slimItem.nameID is not None:
                    cfg.evelocations.Hint(slimItem.itemID, [slimItem.itemID,
                     '',
                     ball.x,
                     ball.y,
                     ball.z,
                     slimItem.nameID])
                elif not (slimItem.categoryID == const.categoryAsteroid or slimItem.groupID == const.groupHarvestableCloud):
                    cfg.evelocations.Hint(slimItem.itemID, [slimItem.itemID,
                     slimItem.name,
                     ball.x,
                     ball.y,
                     ball.z,
                     slimItem.nameID])

        self.broker.ballQueue.non_blocking_put((ownersToPrime,
         tickersToPrime,
         allyTickersToPrime,
         stuffToAdd,
         None,
         locationsToPrime))
        t = blue.os.GetSimTime()
        for ballID, damage in damageDict.iteritems():
            self.damageState[ballID] = (damage, t)

    def AddBalls2(self, chunk):
        state, extraBallData = chunk
        ms = blue.MemStream()
        ms.Write(state)
        self._parent_ReadFullStateFromStream(ms, 2)
        stuffToAdd = []
        ownersToPrime = []
        tickersToPrime = []
        allyTickersToPrime = []
        locationsToPrime = []
        damageTime = blue.os.GetSimTime()
        for data in extraBallData:
            if type(data) is tuple:
                slimItemDict, damageState = data
            else:
                slimItemDict = data
                damageState = None
            slimItem = foo.SlimItem()
            slimItem.__dict__ = slimItemDict
            self.damageState[slimItem.itemID] = (damageState, damageTime)
            if slimItem.itemID in self.slimItems:
                continue
            ball = self.balls[slimItem.itemID]
            if slimItem.itemID > destiny.DSTLOCALBALLS:
                stuffToAdd.append((slimItem.itemID, slimItem))
                if slimItem.categoryID in self.__categoryRequireOwnerPrime__:
                    ownersToPrime.append(slimItem.ownerID)
                    if slimItem.charID is not None:
                        ownersToPrime.append(slimItem.charID)
                        ownersToPrime.append(slimItem.corpID)
                if slimItem.corpID and slimItem.corpID not in tickersToPrime:
                    tickersToPrime.append(slimItem.corpID)
                if slimItem.allianceID and slimItem.allianceID not in allyTickersToPrime:
                    allyTickersToPrime.append(slimItem.allianceID)
                if util.IsCelestial(slimItem.itemID) or util.IsStargate(slimItem.itemID):
                    locationsToPrime.append(slimItem.itemID)
                elif slimItem.itemID >= const.minFakeItem and slimItem.nameID is not None:
                    cfg.evelocations.Hint(slimItem.itemID, [slimItem.itemID,
                     '',
                     ball.x,
                     ball.y,
                     ball.z,
                     slimItem.nameID])
                elif not (slimItem.categoryID == const.categoryAsteroid or slimItem.groupID == const.groupHarvestableCloud):
                    cfg.evelocations.Hint(slimItem.itemID, [slimItem.itemID,
                     slimItem.name,
                     ball.x,
                     ball.y,
                     ball.z,
                     slimItem.nameID])

        self.broker.ballQueue.non_blocking_put((ownersToPrime,
         tickersToPrime,
         allyTickersToPrime,
         stuffToAdd,
         None,
         locationsToPrime))

    def AddClientSideBall(self, position, isGlobal = False):
        x, y, z = position
        ball = self.AddBall(self.clientBallNextID, 1.0, 0.0, 0, False, isGlobal, False, False, False, x, y, z, 0, 0, 0, 0, 0)
        self.clientBallNextID -= 1
        return ball

    def RemoveClientSideBall(self, ballID):
        self._parent_RemoveBall(ballID, 0)

    @telemetry.ZONE_METHOD
    def RemoveBall(self, ballID, terminal = False, bubbleID = -1):
        if self.broker.logInfo:
            self.broker.LogInfo('Removing ball', ballID, '(terminal)' if terminal else '')
        ball = self.balls.get(ballID, None)
        delay = 0
        if hasattr(ball, 'KillBooster'):
            ball.KillBooster()
        if terminal and hasattr(ball, '__class__'):
            delay = const.terminalExplosionDelay
            ball.explodeOnRemove = True
        self._parent_RemoveBall(ballID, delay)
        if ballID in self.damageState:
            del self.damageState[ballID]
        if self.activityByDrone.has_key(ballID):
            del self.activityByDrone[ballID]
        if ballID not in self.slimItems:
            return
        slimItem = self.slimItems[ballID]
        if ballID > destiny.DSTLOCALBALLS:
            if ball is None:
                self.broker.LogWarn('DoBallRemove sending a None ball', slimItem, terminal)
            sm.SendEvent('DoBallRemove', ball, slimItem, terminal)
        if ballID in self.slimItems:
            del self.slimItems[ballID]

    def RemoveBalls(self, ballIDs, exploders = None):
        if exploders and self.broker.logInfo:
            self.broker.LogInfo('RemoveBalls: Has exploders')
        for ballID in ballIDs:
            terminal = False
            if exploders and ballID in exploders:
                terminal = True
            self.RemoveBall(ballID, terminal)

    def GetBallsAndItems(self):
        ballList = []
        for ball in self.balls.itervalues():
            if ball.id in self.slimItems:
                ballList.append((ball, self.slimItems[ball.id]))

        return ballList

    def GetBall(self, ballID):
        return self.balls.get(ballID, None)

    def GetBallById(self, ballID):
        return self.GetBall(ballID)

    def OnFleetStateChange(self, fleetState):
        self.broker.LogInfo('OnFleetStateChange', fleetState)
        self.fleetState = fleetState

    def GetLootRights(self, objectID):
        if self.slimItems.has_key(objectID):
            slim = self.slimItems[objectID]
            return getattr(slim, 'lootRights', None)

    def IsAbandoned(self, objectID):
        if self.slimItems.has_key(objectID):
            slim = self.slimItems[objectID]
            lootRights = getattr(slim, 'lootRights', None)
            if lootRights is not None:
                ownerID, corpID, fleetID, abandoned = lootRights
                return abandoned
        return False

    def HaveLootRight(self, objectID):
        if self.slimItems.has_key(objectID):
            slim = self.slimItems[objectID]
            if session.charid == slim.ownerID:
                return True
            lootRights = getattr(slim, 'lootRights', None)
            if lootRights is not None:
                ownerID, corpID, fleetID, abandoned = lootRights
                if abandoned:
                    return True
                if session.charid == ownerID:
                    return True
                if not util.IsNPCCorporation(session.corpid) and session.corpid in (ownerID, corpID):
                    return True
                if session.fleetid is not None and session.fleetid == fleetID:
                    return True
                if self.broker.crimewatchSvc.CanAttackFreely(slim):
                    return True
        return False

    def OnSlimItemChange(self, itemID, newSlim):
        if self.slimItems.has_key(itemID):
            oldSlim = self.slimItems[itemID]
            self.slimItems[itemID] = newSlim
            sm.ScatterEvent('OnSlimItemChange', oldSlim, newSlim)
            ball = self.GetBall(itemID)
            if ball is not None and hasattr(ball, 'OnSlimItemUpdated'):
                ball.OnSlimItemUpdated(newSlim)

    def OnDroneStateChange(self, itemID, ownerID, controllerID, activityState, typeID, controllerOwnerID, targetID):
        if session.charid != ownerID and session.shipid != controllerID:
            if self.stateByDroneID.has_key(itemID):
                del self.stateByDroneID[itemID]
            if self.activityByDrone.has_key(itemID):
                del self.activityByDrone[itemID]
            sm.ScatterEvent('OnDroneControlLost', itemID)
            return
        state = self.stateByDroneID.get(itemID, None)
        if state is None:
            oldActivityState = None
            self.stateByDroneID.UpdateLI([[itemID,
              ownerID,
              controllerID,
              activityState,
              typeID,
              controllerOwnerID,
              targetID]], 'droneID')
        else:
            state.ownerID = ownerID
            state.controllerID = controllerID
            state.controllerOwnerID = controllerOwnerID
            oldActivityState = state.activityState
            state.activityState = activityState
            state.targetID = targetID
        sm.ScatterEvent('OnDroneStateChange2', itemID, oldActivityState, activityState)

    def OnDroneActivityChange(self, droneID, activityID, activity):
        if not activity:
            if self.activityByDrone.has_key(droneID):
                del self.activityByDrone[droneID]
        else:
            self.activityByDrone[droneID] = (activity, activityID)

    def OnShipStateUpdate(self, shipState):
        if self.broker.logInfo:
            self.broker.LogInfo('OnModuleAttributeChange', shipState)
        for moduleID, moduleState in shipState.iteritems():
            sm.ScatterEvent('OnModuleAttributeChange', *moduleState)

    def OnDamageStateChange(self, shipID, damageState):
        if self.broker.logInfo:
            if util.IsFullLogging():
                self.broker.LogInfo('OnDamageStateChange', shipID, damageState)
            else:
                self.broker.LogInfo('OnDamageStateChange')
        shield = damageState[0]
        self.damageState[shipID] = (damageState, blue.os.GetSimTime())
        sm.ScatterEvent('OnDamageStateChange', shipID, self.GetDamageState(shipID))

    def OnFleetDamageStateChange(self, shipID, damageState):
        if self.broker.logInfo:
            self.broker.LogInfo('OnFleetDamageStateChange', shipID, damageState)
        self.damageState[shipID] = (damageState, blue.os.GetSimTime())
        sm.ScatterEvent('OnFleetDamageStateChange', shipID, self.GetDamageState(shipID))

    def OnSpecialFX(self, shipID, moduleID, moduleTypeID, targetID, otherTypeID, area, guid, isOffensive, start, active, duration = -1, repeat = None, startTime = None, graphicInfo = None):
        if isinstance(moduleID, collections.Iterable):
            for m in moduleID:
                sm.ScatterEvent('OnSpecialFX', shipID, m, moduleTypeID, targetID, otherTypeID, area, guid, isOffensive, start, active, duration, repeat, startTime, graphicInfo)

        else:
            sm.ScatterEvent('OnSpecialFX', shipID, moduleID, moduleTypeID, targetID, otherTypeID, area, guid, isOffensive, start, active, duration, repeat, startTime, graphicInfo)

    def ScatterEwars(self, shipID, moduleID, moduleTypeID, targetID, otherTypeID, area, guid, isOffensive, start, active, duration = -1, repeat = None, startTime = None, graphicInfo = None):
        if isinstance(moduleID, collections.Iterable):
            for m in moduleID:
                sm.ScatterEvent('OnEwarOnConnect', shipID, m, moduleTypeID, targetID)

        else:
            sm.ScatterEvent('OnEwarOnConnect', shipID, moduleID, moduleTypeID, targetID)

    def OnSovereigntyChanged(self, *args):
        sm.ScatterEvent('OnSovereigntyChanged', *args)

    def GetInvItem(self, id):
        return self.slimItems.get(id, None)

    def OnAudioActivated(self):
        for ball in self.balls.itervalues():
            if ball and hasattr(ball, 'SetupAmbientAudio'):
                ball.SetupAmbientAudio()

    def OnActivatingWarp(self, srcID, stamp):
        ball = self.GetBall(srcID)
        if ball is not None:
            if hasattr(ball, 'EnterWarp'):
                ball.EnterWarp()

    def OnDeactivatingWarp(self, srcID, stamp):
        ball = self.GetBall(srcID)
        if ball is not None:
            if hasattr(ball, 'ExitWarp'):
                ball.ExitWarp()