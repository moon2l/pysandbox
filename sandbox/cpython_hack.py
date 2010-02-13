from ctypes import Structure, cast, POINTER, CFUNCTYPE
from ctypes import c_void_p, c_size_t, c_int,  c_char_p
from ctypes import pythonapi
import sys

Py_ssize_t = c_size_t

Py_REF_DEBUG = hasattr(sys, "gettotalrefcount")
Py_TRACE_REFS = Py_REF_DEBUG

# Python 2.6 constant
CO_MAXBLOCKS = 20

class PyObject_HEAD(Structure):
    if Py_TRACE_REFS:
        _fields_ = (
            ("_ob_next", c_void_p), # struct _object*
            ("_ob_prev", c_void_p), # struct _object*
        )
    else:
        _fields_ = tuple()
    _fields_ += (
	("ob_refcnt", Py_ssize_t),
        ("ob_type", c_void_p), # struct _typeobject*
    )
PyObject_HEAD_p = POINTER(PyObject_HEAD)

PyObject_p = PyObject_HEAD_p
PyObject_pp = POINTER(PyObject_p)

class PyObject_VAR_HEAD(Structure):
    _fields_ = PyObject_HEAD._fields_ + (
        ("ob_size", Py_ssize_t),
    )

destructor = CFUNCTYPE(None, c_void_p)

class struct_typeobject(Structure):
    _fields_ = PyObject_VAR_HEAD._fields_ + (
	("tp_name", c_char_p),
        ("tp_basicsize", Py_ssize_t),
	("tp_itemsize", Py_ssize_t),
	("tp_dealloc", destructor),
        # ... we don't need more
    )
struct_typeobject_p = POINTER(struct_typeobject)

class PyTryBlock(Structure):
    _fields_ = (
        ("b_type", c_int),
        ("b_handler", c_int),
        ("b_level", c_int),
    )

class PyFrameObject(Structure):
    # Python 2.6 attributes
    _fields_ = PyObject_VAR_HEAD._fields_ + (
        ("f_back", c_void_p),
        ("f_code", PyObject_p),
        ("f_builtins", PyObject_p),
        ("f_globals", PyObject_p),
        ("f_locals", PyObject_p),
        ("f_valuestack", PyObject_pp),
        ("f_stacktop", PyObject_pp),
        ("f_trace", PyObject_p),
        ("f_exc_type", PyObject_p),
        ("f_exc_value", PyObject_p),
        ("f_exc_traceback", PyObject_p),
        ("f_tstate", c_void_p),
        ("f_lasti", c_int),
        ("f_lineno", c_int),
        ("f_iblock", c_int),
        ("f_blockstack", PyTryBlock * CO_MAXBLOCKS),
        ("f_localsplus", PyObject_pp),
    )

def cptr_at(addresss, type=None):
    if type is not None:
        type = POINTER(type)
    else:
        type = PyObject_p
    if isinstance(addresss, int):
        addresss = c_void_p(addresss)
    return cast(addresss, type)

def cobject_at(address, type=None):
    cobj_ptr = cptr_at(address, type)
    return cobj_ptr.contents

def pyobject_address(obj):
    return id(obj)

def pyobject_get_cptr(pyobj, type=None):
    address = pyobject_address(pyobj)
    return cptr_at(address, type)

def pyobject_get_cobject(pyobj, type=None):
    cptr = pyobject_get_cptr(pyobj, type)
    return cptr.contents

COUNT_ALLOCS = hasattr(pythonapi, 'inc_count')
if COUNT_ALLOCS:
    dec_count = pythonapi.dec_count

def Py_TYPE(cobj_ptr):
    """
    Get op->ob_type as a struct_typeobject_p.
    """
    cobj = cobj_ptr.contents
    return cast(cobj.ob_type, struct_typeobject_p)

if Py_TRACE_REFS:
    _Py_Dealloc = pythonapi._Py_Dealloc
else:
    def _Py_Dealloc(cobj_ptr):
        type_address = Py_TYPE(cobj_ptr)
        if COUNT_ALLOCS:
            dec_count(type_address)
        cobj_type = cobject_at(type_address, struct_typeobject)
        cobj_type.tp_dealloc(cobj_ptr)

def Py_DECREF(cobj_ptr):
    cobj = cobj_ptr.contents
    cobj.ob_refcnt -= 1
    if cobj.ob_refcnt == 0:
        _Py_Dealloc(cobj_ptr)

def Py_INCREF(obj):
    obj.ob_refcnt += 1

def set_frame_builtins(frame, builtins):
    cframe = pyobject_get_cobject(frame, PyFrameObject)
    Py_DECREF(cframe.f_builtins)

    cbuiltins = pyobject_get_cobject(builtins)
    Py_INCREF(cbuiltins)
    cframe.f_builtins = pyobject_get_cptr(builtins)

class ClearFrameCache:
    def __init__(self, frame):
        self.frame = frame
        self.cframe = pyobject_get_cobject(self.frame, PyFrameObject)

        # clear f_locals
        self.locals = frame.f_locals.copy()
        frame.f_locals.clear()

        # clear f_localsplus (LOAD_FAST/STORE_FAST cache)
        self.cache_size = 2
        self.cache = []
        for index in xrange(self.cache_size):
            ptr = self.cframe.f_localsplus[index]
            print "CLEAR CACHE[%s]=%s" % (index, ptr)
            pythonapi._PyObject_Dump(ptr)
            self.cache.append(ptr)
            self.cframe.f_localsplus[index] = pyobject_address(42)

    def restore(self):
        # restore f_localsplus (LOAD_FAST/STORE_FAST cache)
        for index, ptr in enumerate(self.cache):
            self.cframe.f_localsplus[index] = ptr
        # restore f_locals
        self.frame.f_locals.update(self.locals)

