#Embedded file name: c:/depot/games/branches/release/EVE-TRANQUILITY/carbon/common/script/net/machoNetTransport.py
from __future__ import with_statement
import blue
import uthread
import stackless
import sys
import types
import base
import zlib
import weakref
import log
import macho
import service
import bluepy
import const
import httpUtil
import json
import copy
globals().update(service.consts)
from timerstuff import ClockThis
import iocp
from service import ROLE_SERVICE, ROLE_REMOTESERVICE
MACHONET_LOGMOVEMENT = 0
if '/disablePacketCompression' in blue.pyos.GetArg():
    log.general.Log('Packet Compression: Disabled', log.LGINFO)
    MACHONET_COMPRESSION_DISABLED = True
elif iocp.UsingCompression():
    log.general.Log('Packet Compression: IOCP', log.LGINFO)
    if iocp.UsingIOCP():
        import carbonio
        carbonio.setCompressionThreshold(prefs.GetValue('machoNet.minimumBytesToCompress', 200))
        carbonio.setCompressionMinRatio(prefs.GetValue('packetCompressionMinimumRatio', 75))
        carbonio.setCompressionLevel(prefs.GetValue('packetCompressionLevel', 6))
        MACHONET_COMPRESSION_DISABLED = True
    else:
        log.general.Log('Could not turn on IOCP packet compression as IOCP is not enabled!  Reverting to MachoNet compression...', log.LGERR)
        MACHONET_COMPRESSION_DISABLED = False
else:
    log.general.Log('Packet Compression: MachoNet', log.LGINFO)
    MACHONET_COMPRESSION_DISABLED = False
if prefs.GetValue('machoNet.logMovement', 0) or '/logMovement' in blue.pyos.GetArg():
    MACHONET_LOGMOVEMENT = 1

class MachoTransport(log.LogMixin):
    __guid__ = 'macho.MachoTransport'
    __sessioninitorchangenotification__ = (const.cluster.MACHONETMSG_TYPE_SESSIONINITIALSTATENOTIFICATION, const.cluster.MACHONETMSG_TYPE_SESSIONCHANGENOTIFICATION)

    def __init__(self, transportID, transport, transportName, machoNet):
        self.machoNet = weakref.proxy(machoNet)
        log.LogMixin.__init__(self, '%s transport' % self.machoNet.__guid__)
        self.nodeID = None
        self.transportID = transportID
        self.transport = transport
        self.transportName = transportName
        if self.transportName == 'tcp:packet:client':
            self.userID = None
        self.clientID = 0
        self.sessionID = None
        self.clientIDs = {}
        self.dependants = {}
        self.sessions = {}
        self.contextSessions = {}
        self.calls = {}
        self.currentReaders = 0
        if self.transportName == 'tcp:packet:client':
            self.desiredReaders = 2
        else:
            self.desiredReaders = 20
        self.lastPing = None
        self.pinging = False
        self.estimatedRTT = 100 * const.MSEC
        self.timeDiff = 0
        self.compressionThreshold = prefs.GetValue('machoNet.minimumBytesToCompress', 200)
        self.compressionPercentageThreshold = prefs.GetValue('machoNet.maxPercentagePreCompressedToCompress', 75)
        self.largePacketLogSpamThreshold = prefs.GetValue('machoNet.largePacketLogSpamThreshold', None)
        self.dropPacketThreshold = prefs.GetValue('machoNet.dropPacketThreshold', 5000000)

    def __str__(self):
        return repr(self)

    def __repr__(self):
        try:
            return "MachoTransport(nodeID=%s,transportID=%s,transport='%s',transportName='%s',clientID=%s" % (self.nodeID,
             self.transportID,
             str(self.transport),
             self.transportName,
             self.clientID)
        except StandardError:
            sys.exc_clear()
            return 'MachoTransport containing crappy data'

    def LogInfo(self, *args):
        if self.machoNet.isLogInfo:
            log.LogMixin.LogInfo(self, *args)

    def GetMachoAddressOfOtherSide(self):
        if macho.mode == 'client':
            return macho.MachoAddress(nodeID=self.machoNet.myProxyNodeID)
        elif self.clientID:
            return macho.MachoAddress(clientID=self.clientID)
        else:
            return macho.MachoAddress(nodeID=self.nodeID)

    def IsClosed(self):
        return self.transport.IsClosed()

    def HasLegacyClient(self):
        return self.transport is not None

    def Close(self, reason, reasonCode = None, reasonArgs = {}, exception = None, noSend = False):
        if self.machoNet.transportsByID.has_key(self.transportID):
            blue.net.PurgeTransport(self.transportID)
            oldNodeIDByServiceMask = {}
            if self.transportName == 'ip:packet:server' and self.machoNet.namedtransports.has_key('ip:packet:server'):
                self.machoNet.ClearAddressCache()
                self.machoNet.ResetAutoResolveCache()
                del self.machoNet.namedtransports['ip:packet:server']
            if self.nodeID is not None and (self.machoNet.transportIDbyProxyNodeID.has_key(self.nodeID) and self.machoNet.transportIDbyProxyNodeID[self.nodeID] == self.transportID or self.machoNet.transportIDbySolNodeID.has_key(self.nodeID) and self.machoNet.transportIDbySolNodeID[self.nodeID] == self.transportID):
                if not self.machoNet.IsClusterShuttingDown():
                    self.machoNet.LogError('Removing transport from transportIDbyProxyNodeID or transportIDbySolNodeID', self.nodeID, self, reason)
                    log.LogTraceback()
                try:
                    if self.nodeID in self.machoNet.transportIDbyProxyNodeID:
                        del self.machoNet.transportIDbyProxyNodeID[self.nodeID]
                        blue.net.DelProxyNode(self.nodeID)
                except StandardError:
                    sys.exc_clear()
                    self.LogInfo('Exception during MachoTransport::Close ignored.')

                try:
                    if self.nodeID in self.machoNet.transportIDbySolNodeID:
                        del self.machoNet.transportIDbySolNodeID[self.nodeID]
                except StandardError:
                    sys.exc_clear()
                    self.LogInfo('Exception during MachoTransport::Close ignored.')

                oldNodeIDByServiceMask = copy.deepcopy(self.machoNet.nodeIDsByServiceMask)
                self.machoNet.RemoveAllForNode(self.nodeID)
                if macho.mode == 'proxy' and not self.machoNet.IsClusterShuttingDown():
                    self.machoNet.ServerBroadcast('OnNodeDeath', self.nodeID, 1, "The node's transport was detected disconnected by the proxy.   reason code=%s" % strx(reason))
            for each in self.clientIDs.iterkeys():
                try:
                    del self.machoNet.transportIDbyClientID[each]
                except StandardError:
                    sys.exc_clear()
                    self.LogInfo('Exception during MachoTransport::Close ignored.')

            self.clientIDs = {}
            try:
                del self.machoNet.transportIDbySessionID[self.sessionID]
            except StandardError:
                sys.exc_clear()
                self.LogInfo('Exception during MachoTransport::Close ignored.')

            try:
                del self.machoNet.transportsByID[self.transportID]
            except StandardError:
                sys.exc_clear()
                self.LogInfo('Exception during MachoTransport::Close ignored.')

            try:
                self.transport.Close(reason, reasonCode, reasonArgs, exception, noSend)
            except StandardError:
                sys.exc_clear()
                self.LogInfo('Exception during MachoTransport::Close ignored.')

            while self.calls:
                try:
                    k, v = self.calls.items()[0]
                    try:
                        del self.calls[k]
                    finally:
                        v.send_exception(GPSTransportClosed, reason, reasonCode, reasonArgs)

                except Exception:
                    log.LogException('Exception during transport closed broadcast.  (Semi)-silently ignoring this.')
                    sys.exc_clear()

            if not hasattr(self, 'done_broadcasting_close'):
                self.done_broadcasting_close = 1
                if len(self.dependants) and self.transportName == 'tcp:packet:client':
                    msg = macho.TransportClosed(clientID=self.clientID, isRemote=0)
                    msg2 = macho.TransportClosed(clientID=self.clientID, isRemote=1)

                    def CloseTransport(caller, tid, msg):
                        if caller.transportsByID.has_key(tid):
                            try:
                                caller.transportsByID[tid].Write(msg)
                            except StandardError:
                                log.LogTraceback()
                                caller.transportsByID[tid].Close('Write failed big time in CloseTransport')
                                sys.exc_clear()
                            except:
                                log.LogTraceback()
                                caller.transportsByID[tid].Close('Write failed big time in CloseTransport, non-standard error')
                                raise 

                    for tid in self.dependants.iterkeys():
                        uthread.worker('machoNet::CloseTransport', CloseTransport, self.machoNet, tid, msg)
                        msg = msg2

                if self.transportName == 'tcp:packet:client':
                    self.machoNet.LogOffSession(self.sessionID)
                if self.transportName == 'tcp:packet:machoNet':
                    disco = set()
                    for tid in self.machoNet.transportIDbyClientID.itervalues():
                        if self.transportID in self.machoNet.transportsByID[tid].dependants:
                            disco.add(tid)

                    for tid in self.dependants:
                        if self.transportID in self.machoNet.transportsByID[tid].dependants:
                            disco.add(tid)

                    if disco:
                        mappingsForDeadNode = []
                        if prefs.GetValue('DontDisconnectOnClusterSingletonDeath', 0):
                            for serviceID, mapping in oldNodeIDByServiceMask.iteritems():
                                if self.nodeID in mapping:
                                    mappingsForDeadNode.append(serviceID)

                        if mappingsForDeadNode == [const.cluster.SERVICE_CLUSTERSINGLETON]:
                            self.machoNet.LogWarn('NOT Disconnecting %s dependant users even though node %s has gone offline. The node was just servicing clustersingleton services.' % (len(disco), self.nodeID))
                        else:
                            self.machoNet.LogWarn('Disconnecting %s dependant users because node %s has gone offline. The node had the following serviceIDs: %s' % (len(disco), self.nodeID, ','.join([ str(m) for m in mappingsForDeadNode ])))
                            for tid in disco:
                                self.machoNet.transportsByID[tid].Close('A server node you were using has gone offline.', 'NODEDEATH')

                self.dependants = {}
                if self.transportName == 'tcp:packet:machoNet':
                    reason = 'Session terminated due to local transport closure'
                while len(self.sessions):
                    for nodeID in self.sessions.keys():
                        self.SessionClosed(nodeID, reason)

                while len(self.contextSessions):
                    for nodeID in self.contextSessions.keys():
                        self.SessionClosed(nodeID, reason)

    @bluepy.TimedFunction('machoNet::Transport::SessionClosed')
    def SessionClosed(self, clientID, reason, isRemote = 0):
        if self.clientIDs.has_key(clientID):
            del self.clientIDs[clientID]
        if self.machoNet.transportIDbyClientID.has_key(clientID):
            del self.machoNet.transportIDbyClientID[clientID]
        blue.net.PurgeClient(clientID)
        sess = None
        if clientID in self.sessions:
            sess = self.sessions[clientID]
            del self.sessions[clientID]
        if not sess and clientID in self.contextSessions:
            sess = self.contextSessions[clientID]
            del self.contextSessions[clientID]
        if sess:
            with MachoCallOrNotification(self, sess, None):
                mask = sess.Masquerade()
                try:
                    if self.transportName == 'ip:packet:server':
                        sm.ScatterEvent('OnDisconnect', getattr(self, 'disconnectsilently', 0), reason)
                    if macho.mode != 'client':
                        sess.LogSessionHistory(reason)
                        base.CloseSession(sess, isRemote)
                    else:
                        sess.ClearAttributes(dontSendMessage=True)
                finally:
                    mask.UnMask()

    def _JitSessionToOtherSide(self, clientID):
        clientTransportID = self.machoNet.transportIDbyClientID[clientID]
        clientTransport = self.machoNet.transportsByID[clientTransportID]
        remoteSessionVersion = clientTransport.dependants.get(self.transportID, 0)
        sess = clientTransport.sessions[clientID]
        if remoteSessionVersion != sess.version:
            sessData = {}
            self.machoNet.LogInfo('JITing session ', sess.sid, ' (clientID ', clientID, '), localVer = ', sess.version, ' remoteVer = ', remoteSessionVersion)
            if remoteSessionVersion == 0:
                for v in sess.GetDistributedProps(0):
                    sessData[v] = getattr(sess, v)

                sessionprops = macho.SessionInitialStateNotification(source=macho.MachoAddress(clientID=clientID), destination=macho.MachoAddress(nodeID=self.nodeID), sid=sess.sid, sessionType=sess.sessionType, initialstate=sessData)
            else:
                for v in sess.GetDistributedProps(1):
                    sessData[v] = (None, getattr(sess, v))

                sessionprops = macho.SessionChangeNotification(source=macho.MachoAddress(clientID=clientID), destination=macho.MachoAddress(nodeID=self.nodeID), sid=sess.sid, change=(1, sessData))
            clientTransport.dependants[self.transportID] = sess.version
            self.Write(sessionprops, jitSession=0)

    @bluepy.TimedFunction('machoNet::MachoTransport::Write')
    def Write(self, message, jitSession = 1):
        if macho.mode == 'proxy' and jitSession:
            if message.source.addressType == const.ADDRESS_TYPE_CLIENT:
                self._JitSessionToOtherSide(message.source.clientID)
            elif base.IsInClientContext() and session and hasattr(session, 'clientID'):
                clientID = session.clientID
                self._JitSessionToOtherSide(clientID)
                message.contextKey = clientID
                ls = GetLocalStorage()
                message.applicationID = ls.get('applicationID', None)
                message.languageID = ls.get('languageID', None)
        if hasattr(self, 'userID'):
            message.userID = self.userID
        if message.source.addressType == const.ADDRESS_TYPE_ANY and not message.command % 2:
            message.source.nodeID = self.machoNet.nodeID
            message.source.addressType = const.ADDRESS_TYPE_NODE
            message.Changed()
        elif message.source.addressType == const.ADDRESS_TYPE_NODE and message.source.nodeID is None:
            message.source.nodeID = self.machoNet.nodeID
            message.Changed()
        thePickle = message.GetPickle()
        if message.command != const.cluster.MACHONETMSG_TYPE_MOVEMENTNOTIFICATION or MACHONET_LOGMOVEMENT:
            self.LogInfo('Write: ', message)
        if self.transportName != 'tcp:packet:machoNet' and message.compressedPart * 100 / len(thePickle) < self.compressionPercentageThreshold and len(thePickle) - message.compressedPart > self.compressionThreshold and not MACHONET_COMPRESSION_DISABLED:
            before = len(thePickle)
            try:
                with bluepy.Timer('machoNet::MachoTransport::Write::Compress'):
                    compressed = zlib.compress(thePickle, 1)
            except zlib.error as e:
                raise RuntimeError('Compression Failure: ' + strx(e))

            after = len(compressed)
            if after > before:
                self.LogInfo('Compress would have exploded data from ', before, ' to ', after, ' bytes.  Sending uncompressed.')
            elif (before - after) * 100 / before <= 5:
                self.LogInfo("Compress didn't help one bit.  Would have compressed data from ", before, ' to ', after, " bytes, which is insignificant.  Sending uncompressed, rather than wasting the recipient's CPU power for nothing.")
            else:
                thePickle = compressed
                self.machoNet.compressedBytes.Add(before - after)
        if self.transportName == 'tcp:packet:client' and macho.mode == 'proxy':
            for objectID, refID in message.oob.get('OID+', {}).iteritems():
                s = self.sessions.get(self.clientID, None)
                if s is not None:
                    s.RegisterMachoObject(objectID, None, refID)

        if self.largePacketLogSpamThreshold != None and len(thePickle) > self.largePacketLogSpamThreshold:
            log.LogTraceback(extraText='Packet larger than the %d byte largePacketLogSpamTreshhold being written out to wire (%d > %d)' % (self.largePacketLogSpamThreshold, len(thePickle), self.largePacketLogSpamThreshold))
        if len(thePickle) > self.dropPacketThreshold:
            if self.transportName == 'tcp:packet:client' or macho.mode == 'server' and (message.destination.addressType == const.ADDRESS_TYPE_CLIENT or message.destination.addressType == const.ADDRESS_TYPE_BROADCAST and message.destination.idtype not in ('nodeID', '+nodeID')):
                self.machoNet.LogError('Attempted to send a deadly (len=', len(thePickle), ') packet to client(s), PACKET DROPPED')
                self.machoNet.LogError('Packet =', repr(message)[:1024])
                self.machoNet.LogError('Pickle starts with =', repr(thePickle)[:1024])
                return
        self.transport.Write(thePickle)
        self.machoNet.dataSent.Add(len(thePickle))

    @bluepy.TimedFunction('machoNet::MachoTransport::Read')
    def Read(self):
        self.currentReaders += 1
        try:
            thePickle = self.transport.Read()
        finally:
            self.currentReaders -= 1

        if getattr(self, 'userID', None) and len(thePickle) > 100000:
            self.machoNet.LogWarn('Read a ', len(thePickle), ' byte packet (before decompression) from userID=', getattr(self, 'userID', 'non-user'), ' on address ', self.transport.address)
        elif len(thePickle) > 5000000:
            self.machoNet.LogWarn('Read a ', len(thePickle), ' byte packet (before decompression) from userID=', getattr(self, 'userID', 'non-user'), ' on address ', self.transport.address)
        if thePickle[0] not in '}~':
            before = len(thePickle)
            try:
                with bluepy.Timer('machoNet::MachoTransport::Read::DeCompress'):
                    thePickle = zlib.decompress(thePickle)
            except zlib.error as e:
                raise RuntimeError('Decompression Failure: ' + strx(e))

            after = len(thePickle)
            if after <= before:
                self.machoNet.LogError('Decompress shrank data from ', before, ' to ', after, ' bytes')
            else:
                self.machoNet.decompressedBytes.Add(after - before)
        if getattr(self, 'userID', None) and len(thePickle) > 100000:
            self.machoNet.LogWarn('Read a ', len(thePickle), ' byte packet (after decompression, if appropriate) from userID=', getattr(self, 'userID', 'non-user'), ' on address ', self.transport.address)
        elif len(thePickle) > 5000000:
            self.machoNet.LogWarn('Read a ', len(thePickle), ' byte packet (after decompression, if appropriate) from userID=', getattr(self, 'userID', 'non-user'), ' on address ', self.transport.address)
        if self.clientID:
            self.machoNet.dataReceived.Add(len(thePickle))
        else:
            self.machoNet.dataReceived.AddFrom(self.nodeID, len(thePickle))
        try:
            message = macho.Loads(thePickle)
        except GPSTransportClosed as e:
            self.transport.Close(**e.GetCloseArgs())
            raise 
        except StandardError:
            if self.transportName == 'tcp:packet:client':
                self._LogPotentialAttackAndClose(thePickle)
            raise 

        message.SetPickle(thePickle)
        if macho.mode == 'client' and message.source.addressType == const.ADDRESS_TYPE_NODE and message.destination.addressType == const.ADDRESS_TYPE_BROADCAST:
            message.oob['sn'] = self.machoNet.notifySequenceIDByNodeID[message.source.nodeID]
            self.machoNet.notifySequenceIDByNodeID[message.source.nodeID] += 1
        if self.transportName == 'tcp:packet:client':
            message.source = macho.MachoAddress(clientID=self.clientID, callID=message.source.callID)
            if message.contextKey is not None or message.applicationID is not None or message.languageID is not None:
                self._LogPotentialAttackAndClose(thePickle)
                raise StandardError('Packet containing contextKey received on a client transport. Hack?')
        if hasattr(self, 'userID'):
            message.userID = self.userID
        if message.command != const.cluster.MACHONETMSG_TYPE_MOVEMENTNOTIFICATION or MACHONET_LOGMOVEMENT:
            self.LogInfo('Read: ', message)
        if macho.mode == 'proxy':
            for objectID, refID in message.oob.get('OID-', {}).iteritems():
                s = self.sessions.get(self.clientID, None)
                if s is None:
                    s = self.sessions.get(self.nodeID, None)
                if s is not None:
                    s.UnregisterMachoObject(objectID, refID)

        if macho.mode == 'server':
            ls = GetLocalStorage()
            ls['applicationID'] = message.applicationID
            ls['languageID'] = message.languageID
        return message

    def _LogPotentialAttackAndClose(self, thePickle):
        log.LogTraceback()
        address = self.transport.address
        self.transport.Close('An improperly formed or damaged packet was received from your client')
        db = self.machoNet.session.ConnectToAnyService('DB2')
        db.CallProc('zcluster.Attacks_Insert', getattr(self, 'userID', None), address.split(':')[0], int(address.split(':')[1]), strx(thePickle[:2000].replace('\\', '\\\\').replace('\x00', '\\0')))

    def TagPacketSizes(self, req, rsp = None):
        ctk = GetLocalStorage().get('calltimer.key', None)
        if ctk is not None:
            ct = base.GetCallTimes()
            try:
                s = session._Obj()
            except:
                sys.exc_clear()
                s = session

            if s:
                if not s.role & ROLE_SERVICE:
                    if boot.role == 'client':
                        ct = (ct[2], s.calltimes)
                    else:
                        ct = (ct[0], s.calltimes)
                else:
                    ct = (ct[1], s.calltimes)
            else:
                ct = (ct[1],)
            for calltimes in ct:
                if ctk in calltimes:
                    calltimes[ctk][4] += req.GetPickleSize(self.machoNet)
                    if rsp is not None:
                        with bluepy.Timer('machoNet::HandleMessage::SessionCall::TagPacketSizes::GetPickleSize::Rsp'):
                            calltimes[ctk][5] += rsp.GetPickleSize(self.machoNet)

    def InstallSessionIfRequired(self, serviceName, methodName):
        if macho.mode != 'server':
            raise RuntimeError('InstallSessionIfRequired called on %s (should only be called on server)' % macho.mode)
        if not session.contextOnly:
            raise RuntimeError('InstallSessionIfRequired called on full session')
        sess = session.GetActualSession()
        if sess.role & ROLE_SERVICE != 0:
            return False
        service = sm.GetService(serviceName)
        if methodName != 'MachoResolveObject' and (hasattr(service, 'DoSessionChanging') or hasattr(service, 'ProcessSessionChange') or hasattr(service, 'OnSessionChanged')):
            self.machoNet.LogInfo('CTXSESS: Installing session ', sess.sid, ' to call ', serviceName, '::', methodName)
            sess.contextOnly = False
            self.sessions[sess.clientID] = sess
            del self.contextSessions[sess.clientID]
            sess.DelayedInitialStateChange()
            return True
        self.machoNet.LogInfo('CTXSESS: no need to install ', sess.sid, ' before calling ', serviceName, '::', methodName)
        return False

    def RemoveSessionFromServer(self, sess):
        if not (macho.mode == 'proxy' and self.transportName == 'tcp:packet:machoNet'):
            raise RuntimeError('CTXSESS: RemoveSessionFromServer should only be called on a proxy for a proxy/server transport')
        clientTransportID = self.machoNet.transportIDbySessionID.get(sess.sid, None)
        if clientTransportID is not None:
            clientTransport = self.machoNet.transportsByID[clientTransportID]
            if self.transportID in clientTransport.dependants:
                self.machoNet.LogInfo('CTXSESS: Removing dependants entry with version ', clientTransport.dependants[self.transportID])
                del clientTransport.dependants[self.transportID]
            try:
                self.machoNet.LogInfo('CTXSESS: Sending a TransportClosed to remove irrelevant session ', sess.sid, ' (client ', sess.clientID, ')')
                self.Write(macho.TransportClosed(clientID=sess.clientID, isRemote=0))
            except StandardError:
                errStr = 'Write failed in RemoveSessionFromServer(%s)' % (sess.sid,)
                log.LogException(errStr)

    def SessionCall(self, packet):
        try:
            while macho.mode == 'client' and self.machoNet.authenticating:
                blue.pyos.synchro.SleepWallclock(250)

            msgSession, channel, theID = self._SessionAndChannelAndIDFromPacket(packet)
            with MachoCallOrNotification(self, msgSession, packet) as currentcall:
                mask = msgSession.Masquerade({'base.currentcall': weakref.ref(currentcall)})
                packet.srcTransport = self
                try:
                    ret = None
                    if getattr(packet.destination, 'service', None) is not None:
                        if packet.destination.service not in msgSession.connectedServices:
                            try:
                                msgSession.connectedServices[packet.destination.service] = packet.service = msgSession.ConnectToService(packet.destination.service, remote=1)
                            except ServiceNotFound as e:
                                ret = packet.ErrorResponse(const.cluster.MACHONETERR_WRAPPEDEXCEPTION, (macho.DumpsSanitized(e),))
                                sys.exc_clear()

                        else:
                            packet.service = msgSession.connectedServices[packet.destination.service]
                    if ret is None:
                        if channel in self.machoNet.channelHandlersUp:
                            ret = self.machoNet.channelHandlersUp[channel].CallUp(packet)
                        else:
                            ret = packet.ErrorResponse(const.cluster.MACHONETERR_UNMACHOCHANNEL, 'The specified channel is not present on this server')
                    self.TagPacketSizes(packet, ret)
                    return ret
                finally:
                    if msgSession.clientID not in (theID, packet.contextKey):
                        if msgSession.clientID is not None:
                            self.machoNet.LogError('Cleaning session ', msgSession.clientID, " because it's ID doesn't match ", theID)
                        self._CleanupSession(theID)
                    mask.UnMask()
                    if hasattr(packet, 'service'):
                        delattr(packet, 'service')

        except Exception as e:
            log.LogException('Error in session call')
            raise 

    def SessionNotification(self, packet):
        while macho.mode == 'client' and self.machoNet.authenticating:
            blue.pyos.synchro.SleepWallclock(250)

        msgSession, channel, theID = self._SessionAndChannelAndIDFromPacket(packet)
        with MachoCallOrNotification(self, msgSession, packet) as currentcall:
            mask = msgSession.Masquerade({'base.currentcall': weakref.ref(currentcall)})
            packet.srcTransport = self
            try:
                if getattr(packet.destination, 'service', None) is not None:
                    if packet.destination.service not in msgSession.connectedServices:
                        msgSession.connectedServices[packet.destination.service] = msgSession.ConnectToService(packet.destination.service, remote=1)
                    packet.service = msgSession.connectedServices[packet.destination.service]
                if channel in self.machoNet.channelHandlersUp:
                    self.machoNet.channelHandlersUp[channel].NotifyUp(packet)
                else:
                    self.LogInfo('Notification received for channel ', channel, ', but no GPCS handler available for that particular channel of transport', self)
                self.TagPacketSizes(packet)
            finally:
                if msgSession.clientID not in (theID, packet.contextKey):
                    if msgSession.clientID is not None:
                        self.machoNet.LogError('Cleaning session ', msgSession.clientID, " because it's ID doesn't match ", theID)
                    self._CleanupSession(theID)
                mask.UnMask()
                if hasattr(packet, 'service'):
                    delattr(packet, 'service')

    def _SessionFromClientID(self, clientID):
        s = self.sessions.get(clientID, None)
        if s is not None:
            return s[0]
        else:
            return

    def _SessionAndChannelAndIDFromPacket(self, packet):
        if macho.mode == 'server' and packet.contextKey:
            clientID = packet.source.nodeID
            rsess = self.sessions.get(packet.contextKey, None)
            if rsess is None:
                rsess = self.contextSessions[packet.contextKey]
        else:
            clientID, rsess = self._AssociateWithSession(packet)
        channel = None
        if packet is not None:
            channel = macho.packetTypeChannelMap.get(packet.command, None)
        return (rsess, channel, clientID)

    def _CleanupSession(self, theID):
        if macho.mode != 'client':
            sess = None
            if theID in self.sessions:
                sess = self.sessions[theID]
                del self.sessions[theID]
            if not sess and theID in self.contextSessions:
                sess = self.contextSessions[theID]
                del self.contextSessions[theID]
            if sess:
                base.CloseSession(sess)

    def LockSession(self, sess, packet):
        if packet is not None and not packet.command % 2:
            if hasattr(packet, 'sessionVersion'):
                sleepNum = 1
                while packet.sessionVersion > sess.version:
                    logargs1 = ('Sleep #',
                     sleepNum,
                     ' while waiting for session change to complete.  The packet is destined for session version ',
                     packet.sessionVersion,
                     ' but the session(',
                     sess.sid,
                     ') is currently version ',
                     sess.version)
                    logargs2 = ('packet=', packet)
                    if sleepNum % 250 == 0:
                        self.LogError(*logargs1)
                        self.LogError(*logargs2)
                    else:
                        self.LogInfo(*logargs1)
                        self.LogInfo(*logargs2)
                    blue.pyos.synchro.SleepWallclock(500)
                    sleepNum += 1

            self.machoNet.WaitForSequenceNumber(packet.source, packet.oob.get('sn', 0))
        if sess.rwlock:
            if packet is None or packet.command in self.__sessioninitorchangenotification__:
                sess.rwlock.WRLock()
                if sess.role & ROLE_SERVICE:
                    sess.rwlock.Unlock()
                    sess.LogSessionError('SESSIONFUXUP', 'Trying to run a session init or change in a service session context')
                    log.LogTraceback()
                    raise RuntimeError('Session map failure, attempting to run a session init or change in a service session context')
            else:
                sess.rwlock.RDLock()

    def UnLockSession(self, sess, tasklet = None):
        if sess.rwlock:
            sess.rwlock.Unlock(tasklet)

    def _AssociateWithSession(self, packet = None, forceNodeID = None):
        if forceNodeID is not None:
            nodeID = forceNodeID
            serviceSession = True
        elif macho.mode == 'client':
            nodeID = 0
            serviceSession = False
        elif not packet.command % 2:
            if packet.source.addressType == const.ADDRESS_TYPE_CLIENT:
                nodeID = packet.source.clientID
                serviceSession = False
            else:
                nodeID = packet.source.nodeID
                serviceSession = True
        elif packet.destination.addressType == const.ADDRESS_TYPE_CLIENT:
            nodeID = packet.destination.clientID
            serviceSession = False
        else:
            nodeID = packet.destination.nodeID
            serviceSession = True
        sess = self.sessions.get(nodeID, None)
        if not sess:
            sess = self.contextSessions.get(nodeID, None)
        if not sess:
            if macho.mode == 'client':
                sess = session
            elif serviceSession:
                sess = base.GetServiceSession('remote:%d' % nodeID, True)
            elif not packet.command % 2:
                if not isinstance(packet, macho.SessionInitialStateNotification):
                    log.LogTraceback('Packet received before initial session notification. Packet/tasklet reordering?')
                    raise SessionUnavailable('Unable to load session for request')
                sess = base.CreateSession(packet.sid, packet.sessionType)
            else:
                raise UnMachoDestination('Failed session association: cmd = %s, mode = %s' % (packet.command, macho.mode))
            sess.__dict__['clientID'] = nodeID
            if sess.contextOnly:
                self.contextSessions[nodeID] = sess
            else:
                self.sessions[nodeID] = sess
            if serviceSession:
                role = sess.__dict__['role'] | ROLE_SERVICE | ROLE_REMOTESERVICE
                sess.SetAttributes({'role': role})
                sess.LogSessionHistory('machoNet associated remote service session with clientID/nodeID %s' % nodeID)
            else:
                sess.__dict__['rwlock'] = uthread.RWLock(('sessions', sess.sid))
                packetUserID = None if packet is None else packet.userID
                if packetUserID is not None:
                    sess.SetAttributes({'userid': packetUserID})
                sess.LogSessionHistory('machoNet associated session with clientID %s and userID %s' % (nodeID, packetUserID))
        sess.lastRemoteCall = blue.os.GetWallclockTime()
        return (nodeID, sess)


class MachoCallOrNotification(object):

    def __init__(self, transport, sess, packet):
        self.transport, self.sess, self.packet = transport, sess, packet
        self.tasklet = stackless.getcurrent()

    def __enter__(self):
        self.transport.LockSession(self.sess, self.packet)
        return self

    def __exit__(self, e, v, tb):
        self.Unlock(None)

    def UnLockSession(self):
        self.Unlock(self.tasklet)

    def Unlock(self, tasklet):
        if self.sess:
            s = self.sess
            t = self.transport
            self.transport = self.sess = self.tasklet = None
            t.UnLockSession(s, tasklet)

    def __repr__(self):
        return '<MachoCallOrNotification, packet=%r>' % (self.packet,)


class StreamingHTTPMachoTransport(MachoTransport):
    __guid__ = 'macho.StreamingHTTPMachoTransport'

    def __init__(self, transportID, transport, transportName, machoNet):
        MachoTransport.__init__(self, transportID, transport, transportName, machoNet)
        self.readers = set()

    def AddReader(self, reader):
        self.LogInfo('Adding reader to %s' % self)
        self.readers.add(reader)

    def RemoveReader(self, reader):
        self.readers.discard(reader)
        self.LogInfo('Removed reader from %s, %s readers left' % (self, len(self.readers)))

    @bluepy.TimedFunction('machoNet::StreamingHTTPMachoTransport::Close')
    def Close(self, reason, reasonCode = None, reasonArgs = {}, exception = None, noSend = False):
        for reader in self.readers:
            reader.close()

        MachoTransport.Close(self, reason, reasonCode, reasonArgs, exception, noSend)

    @bluepy.TimedFunction('machoNet::StreamingHTTPMachoTransport::Write')
    def Write(self, message):
        if self.transport:
            MachoTransport.Write(self, message)
        if len(self.readers) > 0 and message.command == const.cluster.MACHONETMSG_TYPE_NOTIFICATION:
            with bluepy.Timer('machoNet::StreamingHTTPMachoTransport::Write::MPT-Megahack'):
                sent = False
                try:
                    data = message.__getstate__()
                    if data[0] == 12:
                        if data[2].__getstate__()[1] == '__MultiEvent':
                            self.LogInfo('Splitting __MultiEvent into multiple chunks')
                            jsonMessage = json.loads(httpUtil.ToComplexJSON(data))
                            innerMessages = jsonMessage[4][0][1][1][1]
                            innerMessage = (12,
                             None,
                             [[], None],
                             None,
                             [[0, [0, [1, None]]]])
                            with bluepy.Timer('machoNet::StreamingHTTPMachoTransport::Write::MPT-Megahack::Multiplex'):
                                for msg in innerMessages:
                                    innerMessage[2][1] = msg[0]
                                    innerMessage[4][0][1][1][1] = msg[1]
                                    for reader in self.readers:
                                        reader.write(innerMessage)

                                sent = True
                except:
                    self.LogError('MultiEvent exception', message)
                    log.LogException()

            with bluepy.Timer('machoNet::StreamingHTTPMachoTransport::Write::Multiplex'):
                if not sent:
                    for reader in self.readers:
                        reader.write(message)