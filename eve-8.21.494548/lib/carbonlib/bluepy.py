#Embedded file name: c:\depot\games\branches\release\EVE-TRANQUILITY\carbon\common\lib\bluepy.py
import stackless, weakref
import blue
import sys
import traceback
import functools
import decorator
import types
import util
import time
import os
tasklet_id = 0

class TaskletExt(stackless.tasklet):
    __slots__ = ['context',
     'localStorage',
     'storedContext',
     'startTime',
     'endTime',
     'runTime',
     'tasklet_id']

    @staticmethod
    def GetWrapper(method):
        if not callable(method):
            raise TypeError('TaskletExt::__new__ argument "method" must be callable.')

        def CallWrapper(*args, **kwds):
            current = stackless.getcurrent()
            current.startTime = blue.os.GetWallclockTimeNow()
            oldtimer = PushTimer(current.context)
            exc = None
            try:
                try:
                    return method(*args, **kwds)
                except TaskletExit as e:
                    import log
                    t = stackless.getcurrent()
                    log.general.Log('tasklet (%s) %s exiting with %r' % (t.tasklet_id, t, e), log.LGINFO)
                except SystemExit as e:
                    import log
                    log.general.Log('system %s exiting with %r' % (stackless.getcurrent(), e), log.LGINFO)
                except Exception:
                    import log
                    print >> debugFile, 'Unhandled exception in tasklet', repr(stackless.getcurrent())
                    traceback.print_exc(file=debugFile)
                    exc = sys.exc_info()
                    log.LogException('Unhandled exception in %r' % stackless.getcurrent())

                return
            except:
                traceback.print_exc()
                traceback.print_exc(file=debugFile)
                if exc:
                    traceback.print_exception(exc[0], exc[1], exc[2])
                    traceback.print_exception(exc[0], exc[1], exc[2], file=debugFile)
            finally:
                exc = None
                PopTimer(oldtimer)
                current.endTime = blue.os.GetWallclockTimeNow()

        return CallWrapper

    def __new__(self, ctx, method = None):
        global tasklet_id
        tid = tasklet_id
        tasklet_id += 1
        self.tasklet_id = tid
        if method:
            t = stackless.tasklet.__new__(self, self.GetWrapper(method))
        else:
            t = stackless.tasklet.__new__(self)
        c = stackless.getcurrent()
        ls = getattr(c, 'localStorage', None)
        if ls is None:
            t.localStorage = {}
        else:
            t.localStorage = dict(ls)
        t.storedContext = t.context = ctx
        t.runTime = 0.0
        tasklets[t] = True
        return t

    def bind(self, callableObject):
        return stackless.tasklet.bind(self, self.CallWrapper(callableObject))

    def __repr__(self):
        abps = [ getattr(self, attr) for attr in ['alive',
         'blocked',
         'paused',
         'scheduled'] ]
        abps = ''.join((str(int(flag)) for flag in abps))
        return '<TaskletExt object at %x, abps=%s, ctxt=%r>' % (id(self), abps, getattr(self, 'storedContext', None))

    def __reduce__(self):
        return (str, ("__reduce__()'d " + repr(self),))

    def PushTimer(self, ctxt):
        blue.pyos.taskletTimer.EnterTasklet(ctxt)

    def PopTimer(self, ctxt):
        blue.pyos.taskletTimer.ReturnFromTasklet(ctxt)

    def GetCurrent(self):
        blue.pyos.taskletTimer.GetCurrent()

    def GetWallclockTime(self):
        return (blue.os.GetWallclockTimeNow() - self.startTime) * 1e-07

    def GetRunTime(self):
        return self.runTime + blue.pyos.GetTimeSinceSwitch()


tasklets = weakref.WeakKeyDictionary()

def Shutdown(exitprocs):

    def RunAll():
        stackless.getcurrent().block_trap = True
        for proc in exitprocs:
            try:
                proc()
            except Exception:
                import log
                log.LogException('exitproc ' + repr(proc), toAlertSvc=False)
                sys.exc_clear()

    if exitprocs:
        TaskletExt('Shutdown', RunAll)()
        intr = stackless.run(1000000)
        if intr:
            log.general.Log('ExitProcs interrupted at tasklet ' + repr(intr), log.LGERR)
    GetTaskletDump(True)
    if len(tasklets):
        KillTasklets()
        GetTaskletDump(True)


def GetTaskletDump(logIt = True):
    import log
    lines = []
    lines.append('GetTaskletDump:  %s TaskletExt objects alive' % len(tasklets))
    lines.append('[context] - [code] - [stack depth] - [creation context]')
    for t in tasklets.keys():
        try:
            if t.frame:
                stack = traceback.extract_stack(t.frame, 1)
                depth = len(stack)
                f = stack[-1]
                code = '%s(%s)' % (f[0], f[1])
            else:
                code, depth = ('<no frame>', 0)
        except Exception as e:
            code, depth = repr(e), 0

        ctx = (getattr(t, 'context', '(unknown)'),)
        sctx = getattr(t, 'storedContext', '(unknown)')
        l = '%s - %s - %s - %s' % (sctx,
         code,
         depth,
         ctx)
        lines.append(l)

    lines.append('End TaskletDump')
    if logIt:
        for l in lines:
            log.general.Log(l, log.LGINFO)

    return '\n'.join(lines) + '\n'


def KillTasklets():
    t = TaskletExt('KillTasklets', KillTasklets_)
    t()
    t.run()


def KillTasklets_():
    import log
    log.general.Log('killing all %s TaskletExt objects' % len(tasklets), log.LGINFO)
    for i in range(3):
        for t in tasklets.keys():
            if t is stackless.getcurrent():
                continue
            try:
                if t.frame:
                    log.general.Log('killing %s' % t, log.LGINFO)
                    t.kill()
                else:
                    log.general.Log('ignoring %r, no frame.' % t, log.LGINFO)
            except RuntimeError as e:
                log.general.Log("couldn't kill %r: %r" % (t, e), log.LGWARN)

    log.general.Log('killing done', log.LGINFO)


class DebugFile(object):

    def __init__(self):
        import blue
        self.ODS = blue.win32.OutputDebugString

    def close(self):
        pass

    def flush(self):
        pass

    def write(self, str):
        self.ODS(str)

    def writelines(self, lines):
        for l in lines:
            self.ODS(l)


debugFile = DebugFile()

class PyResFile(object):
    __slots__ = ['rf',
     'name',
     'mode',
     'softspace']

    def __init__(self, path, mode = 'r', bufsize = -1):
        self.rf = blue.ResFile()
        self.mode = mode
        self.name = path
        if 'w' in mode:
            try:
                self.rf.Create(path)
            except:
                raise IOError, 'could not create ' + path

        else:
            readonly = 'a' not in mode and '+' not in mode
            try:
                self.rf.OpenAlways(path, readonly, mode)
            except:
                raise IOError, 'could not open ' + path

    def read(self, count = 0):
        try:
            return self.rf.read(count)
        except:
            raise IOError, 'could not read %d bytes from %s' % (count, self.rf.filename)

    def write(self, data):
        raise NotImplemented

    def readline(self, size = 0):
        raise NotImplemented

    def readlines(self, sizehint = 0):
        r = []
        while True:
            l = self.readline()
            if not l:
                return r
            r.append(l)

    def writelines(self, iterable):
        for i in iterable:
            self.write(i)

    def seek(self, where, whence = 0):
        if whence == 1:
            where += self.rf.pos
        elif whence == 2:
            where += self.rf.size
        try:
            self.rf.Seek(where)
        except:
            raise IOError, 'could not seek to pos %d in %s' % (where, self.rf.filename)

    def tell(self):
        return self.rf.pos

    def truncate(self, size = None):
        if size is None:
            size = self.rf.pos
        try:
            self.rf.SetSize(size)
        except:
            raise IOError, 'could not trucated file %s to %d bytes' % (self.rf.filename, size)

    def flush():
        pass

    def isatty():
        return False

    def close(self):
        self.rf.close()
        del self.rf

    def next(self):
        l = self.readline()
        if l:
            return l
        raise StopIteration

    def __iter__(self):
        return self


def PushTimer(ctxt):
    return blue.pyos.taskletTimer.EnterTasklet(ctxt)


def PopTimer(old):
    return blue.pyos.taskletTimer.ReturnFromTasklet(old)


def CurrentTimer():
    return blue.pyos.taskletTimer.GetCurrent()


EnterTasklet = blue.pyos.taskletTimer.EnterTasklet
ReturnFromTasklet = blue.pyos.taskletTimer.ReturnFromTasklet

class Timer(object):
    __slots__ = ['ctxt']

    def __init__(self, context):
        self.ctxt = context

    def __enter__(self):
        self.ctxt = EnterTasklet(self.ctxt)

    def __exit__(self, type, value, tb):
        ReturnFromTasklet(self.ctxt)
        return False


class TimerPush(Timer):
    GetCurrent = blue.pyos.taskletTimer.GetCurrent

    def __init__(self, context):
        Timer.__init__(self, '::'.join((self.GetCurrent(), context)))


def TimedFunction(ctxt = None):

    def Helper(func):
        myctxt = ctxt if ctxt else repr(func)

        @functools.wraps(func)
        def Wrapper(*args, **kwargs):
            back = EnterTasklet(ctxt)
            try:
                return func(*args, **kwargs)
            finally:
                ReturnFromTasklet(back)

        return Wrapper

    return Helper


def TimedFunction2(context):

    def Wrapper(function, *args, **kwargs):
        back = EnterTasklet(context or repr(function))
        try:
            return function(*args, **kwargs)
        finally:
            ReturnFromTasklet(back)

    return decorator.decorator(Wrapper)


blue.TaskletExt = TaskletExt
blue.tasklets = tasklets
stackless.taskletext = TaskletExt

def GetBlueInfo(numMinutes = None, isYield = True):
    if numMinutes:
        trend = blue.pyos.cpuUsage[-numMinutes * 60 / 10:]
    else:
        trend = blue.pyos.cpuUsage[:]
    mega = 1.0 / 1024.0 / 1024.0
    ret = util.KeyVal()
    ret.memData = []
    ret.pymemData = []
    ret.bluememData = []
    ret.othermemData = []
    ret.threadCpuData = []
    ret.procCpuData = []
    ret.threadKerData = []
    ret.procKerData = []
    ret.timeData = []
    ret.latenessData = []
    ret.schedData = []
    latenessBase = 100000000.0
    if len(trend) >= 1:
        ret.actualmin = int((trend[-1][0] - trend[0][0]) / 10000000.0 / 60.0)
        t1 = trend[0][0]
    benice = blue.pyos.BeNice
    mem = 0
    for t, cpu, mem, sched in trend:
        if isYield:
            benice()
        elap = t - t1
        t1 = t
        p_elap = 100.0 / elap if elap else 0.0
        mem, pymem, workingset, pagefaults, bluemem = mem
        ret.memData.append(mem * mega)
        ret.pymemData.append(pymem * mega)
        ret.bluememData.append(bluemem * mega)
        othermem = (mem - pymem - bluemem) * mega
        if othermem < 0:
            othermem = 0
        ret.othermemData.append(othermem)
        thread_u, proc_u = cpu[:2]
        thread_k, proc_k = cpu[2:4] if len(cpu) >= 4 else (0, 0)
        thread_cpupct = thread_u * p_elap
        proc_cpupct = proc_u * p_elap
        thread_kerpct = thread_k * p_elap
        proc_kerpct = proc_k * p_elap
        ret.threadCpuData.append(thread_cpupct)
        ret.procCpuData.append(proc_cpupct)
        ret.threadKerData.append(thread_kerpct)
        ret.procKerData.append(proc_kerpct)
        ret.schedData.append(sched)
        ret.timeData.append(t)
        late = 0.0
        if elap:
            late = (elap - latenessBase) / latenessBase * 100
        ret.latenessData.append(late)

    ret.proc_cpupct = proc_cpupct
    ret.mem = mem
    return ret


def IsRunningStartupTest():
    args = blue.pyos.GetArg()
    for i, each in enumerate(args):
        if each.startswith('/startupTest'):
            return True

    return False


def TerminateStartupTest():
    blue.os.Terminate(31337)


def TerminateStartupTestWithFailure():
    blue.os.Terminate(1)


def Terminate(reason = ''):
    import log
    log.general.Log('bluepy.Terminate - Reason: %s' % reason, log.LGNOTICE)
    try:
        if 'sm' in __builtins__:
            sm.ChainEvent('ProcessShutdown')
    except:
        log.LogException()

    blue.os.Terminate(0)


import unittest

class BlueFunctionTestCase(unittest.FunctionTestCase):

    def __str__(self):
        return '%s' % self._testFunc.__name__

    def __doc__(self):
        return self._testFunc.__doc__

    def shortDescription(self):
        return None


class BlueTestLoader(unittest.TestLoader):
    suiteClass = unittest.TestSuite

    def loadTestsFromModule(self, module, use_load_tests = True):
        tests = []
        for name in dir(module):
            if name.startswith('test'):
                obj = getattr(module, name)
                tests.append(BlueFunctionTestCase(obj))

        tests = self.suiteClass(tests)
        return tests


del unittest