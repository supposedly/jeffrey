import inspect
import shlex
import sys

from .core import CLI
from .misc import _Null, ErgoNamespace, convert


class Simpleton:
    _ = '-'
    no_help = False
    short_flags = True
    used = False

    def __init__(self, func, cli=None):
        self.cli = cli or CLI(no_help=self.no_help)
        # Fossilize these so if they're changed on the class it doesn't modify instance
        self.no_help = self.no_help
        self.short_flags = self.short_flags
        self._ = self._
        
        if self.used:
            raise ValueError('Cannot have more than one function per simple command/CLI')
        self.used = True
        
        self._consuming = False
        self.commands = {}
        
        self._callback = func
        self._params = inspect.signature(func).parameters.values()
        self.cli.desc = func.__doc__ or ''
        
        pos = [i for i in self._params if i.kind <= inspect.Parameter.VAR_POSITIONAL]
        flags = [i for i in self._params if i.kind == inspect.Parameter.KEYWORD_ONLY]
        self._consuming = pos and pos[-1].kind == inspect.Parameter.VAR_POSITIONAL
        self._add_flargs(self.cli, pos, flags)
    
    def __call__(self, *args, **kwargs):
        return self._callback(*args, **kwargs)
    
    @staticmethod
    def _null_check(val):
        return val is _Null or val is inspect._empty

    def _add_flargs(self, cli, pos, flags):
        for arg in pos:
            if arg.kind == inspect.Parameter.VAR_POSITIONAL:
                def __hidden(arg):
                    def __(nsp, value):
                        nsp.accum.append(convert(arg.annotation, value))
                        return nsp.accum
                    __.__name__ = arg.name
                    return __
                cli.arg(
                  Ellipsis,
                  namespace={'accum': []},
                  required=False,
                  default=_Null if self._null_check(arg.default) else arg.default,
                )(__hidden(arg))
            else:
                def __hidden(arg):
                    def __(value):
                        return convert(arg.annotation, value)
                    __.__name__ = arg.name
                    return __
                cli.arg(
                  required=self._null_check(arg.default),
                  default=_Null if self._null_check(arg.default) else arg.default,
                )(__hidden(arg))
        
        for flag in flags:
            def __hidden(flag):
                def __(value):
                    return convert(flag.annotation, value)
                __.__name__ = flag.name
                return __
            cli.flag(
              short=_Null if self.short_flags else None,
              default=_Null if self._null_check(flag.default) else flag.default,
              _=self._
            )(__hidden(flag))
    
    def command(self, func):
        self.commands[func.__name__] = cmd = Simpleton(func, self.cli.command(func.__name__, _=self._))
        cmd.no_help = self.no_help
        cmd.short_flags = self.short_flags
        cmd._ = self._
        return cmd
    
    def call(self, **flags):
        args = []
        for name, val in flags.copy().items():
            if isinstance(val, ErgoNamespace):
                self.commands[name].call(**dict(val._.items()))
                del flags[name]
            elif name in self._params:
                args.append(flags.pop(name))
        
        args = [
          flags.pop(p.name, ())
            if p.kind == inspect.Parameter.VAR_POSITIONAL
          else flags.pop(p.name)
            if p.name in flags or p.default is inspect._empty
          else p.default
          for p in self._params
          if p.kind <= inspect.Parameter.VAR_POSITIONAL
          ]
        
        if self._consuming:
            args.extend(args.pop(-1))
        return self._callback(*args, **flags)
    
    def run(self, inp=None):
        return self.call(**dict(self.cli.parse(inp)._.items()))
    
    def search(self, inp):
        if inp is None:
            inp = sys.argv[1:]
        if isinstance(inp, str):
            inp = shlex.split(inp)
        if not isinstance(self.cli, CLI):
            try:
                idx = next(
                  i for i, v in enumerate(inp)
                  if v == self._callback.__name__
                  and not
                  (inp[i-1].startswith(self.cli.flag_prefix) or '=' in inp[i-1].lstrip(self.cli.flag_prefix))
                  )
            except StopIteration:
                raise IndexError('command invocation {!r} not found in input'.format(self._callback.__name__))
            inp = inp[idx:]
        return self.run(inp)


sys.modules[__name__] = Simpleton