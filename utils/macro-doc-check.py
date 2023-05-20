#!/usr/bin/python3

import argparse
import dataclasses
import re
import sys
from dataclasses import dataclass
from enum import Enum
from typing import Literal


State = Enum(
    "State",
    [
        "PRE_COMMENT",
        "COMMENT_TEXT",
        "COMMENT_LIST",
        "COMMENT_CMD",
        "COMMENT_PARAM",
        "COMMENT_TYPE",
        "COMMENT_END",
        "MACRO_DEF",
        "MACRO_BODY",
        "MACRO_BODY_STATEMENT",
        "MACRO_BODY_EXPRESSION",
    ],
)

KNOWN_TYPES = set(
    (
        "bool",
        "char",
        "float",
        "int",
        "str",
        "None",
    )
)


@dataclass
class Jinjatype:
    orig: str

    def out(self, name, fmt="if", is_or=False) -> list[str]:
        pass


@dataclass
class JinjatypeSimple(Jinjatype):
    orig: str

    def __repr__(self) -> str:
        return self.orig

    def out(self, name, fmt="if", is_or=False) -> list[str]:
        msg = None
        out = []
        if self.orig == "bool":
            msg = "boolean"
        elif self.orig == "int":
            msg = "integer"
        elif self.orig == "float":
            msg = "float"
        elif self.orig == "str":
            msg = "string"
        elif self.orig == "char":
            if is_or:
                out.append(
                    "{fmt} ({name} is string) and (({name} | length) == 1)".format(
                        name=name, fmt=fmt
                    )
                )
            else:
                out.append(
                    "{fmt} not(({name} is string) and (({name} | length) == 1))".format(
                        name=name, fmt=fmt
                    )
                )
        elif self.orig == "None":
            msg = "none"
        else:
            assert self.orig is None, "unknown type {fmt} {name} {0}".format(
                self.orig, name=name, fmt=fmt
            )
        if is_or:
            if msg is not None:
                out.append("{fmt} {name} is {msg}".format(name=name, fmt=fmt, msg=msg))
        else:
            if msg is not None:
                out.append(
                    "{fmt} {name} is not {msg}".format(name=name, fmt=fmt, msg=msg)
                )
            out.extend(
                [
                    """raise("{name} is not '{orig}'")""".format(
                        name=name, orig=str(self)
                    ),
                    "endif",
                ]
            )
        return out


@dataclass
class JinjatypeList(Jinjatype):
    elem: Jinjatype

    def __repr__(self) -> str:
        return "list[{}]".format(self.elem)

    def out(self, name, fmt="if", is_or=False) -> list[str]:
        out = []
        if is_or:
            out.append(
                "{fmt} ({name} is sequence) and ({name} is not mapping) and ({name} is not string)".format(
                    name=name, fmt=fmt
                )
            )
        else:
            out.extend(
                [
                    "{fmt} not(({name} is sequence) and ({name} is not mapping) and ({name} is not string))".format(
                        name=name, fmt=fmt
                    ),
                    """raise("{name} is not '{orig}'")""".format(
                        name=name, orig=str(self)
                    ),
                    "endif",
                ]
            )
        out.append("for elem_{name} in {name}".format(name=name))
        out.extend(self.elem.out("elem_{name}".format(name=name)))
        out.append("endfor")
        return out


@dataclass
class JinjatypeDict(Jinjatype):
    key: Jinjatype
    value: Jinjatype

    def __repr__(self) -> str:
        return "dict[{}, {}]".format(self.key, self.value)

    def out(self, name, fmt="if", is_or=False) -> list[str]:
        out = []
        if is_or:
            out.append("{fmt} {name} is mapping".format(name=name, fmt=fmt))
        else:
            out.extend(
                [
                    "{fmt} {name} is not mapping".format(name=name, fmt=fmt),
                    """raise("{name} is not '{orig}'")""".format(
                        name=name, orig=str(self)
                    ),
                    "endif",
                ]
            )
        out.append("for key_{name}, value_{name} in {name}".format(name=name))
        out.extend(self.key.out("key_{name}".format(name=name)))
        out.extend(self.value.out("value_{name}".format(name=name)))
        out.append("endfor")
        return out


@dataclass
class JinjatypeOr(Jinjatype):
    values: list[Jinjatype]

    def __repr__(self) -> str:
        out = []
        for v in self.values:
            out.append("{}".format(v))
        return " | ".join(out)

    def out(self, name, fmt="if", is_or=False) -> list[str]:
        out: list[str] = []
        for v in self.values:
            if len(out) == 0:
                out.extend(v.out(name, fmt="if", is_or=True))
            else:
                out.extend(v.out(name, fmt="elif", is_or=True))
        out.extend(
            [
                "else",
                """raise("{name} is not '{orig}'")""".format(name=name, orig=str(self)),
                "endif",
            ]
        )
        return out


@dataclass
class Param:
    desc: list[str] = dataclasses.field(default_factory=list)
    type_: None | str = None
    type_r: None | Jinjatype = None
    default: None | str = None
    seen_in_body: bool = False
    seen_in_def: bool = False
    seen_in_doc: bool = False


@dataclass
class Context:
    file: str
    args: argparse.Namespace
    lineno: int = 0
    line: str = ""
    state: State = State.PRE_COMMENT
    indent: None | str = None
    param_name: None | str = None
    empty: bool = False
    list_style: None | str = None
    macro_name: None | str = None
    params: dict[str, Param] = dataclasses.field(default_factory=dict)

    def clean(self) -> None:
        self.state = State.PRE_COMMENT
        self.indent = None
        self.param_name = None
        self.empty = False
        self.list_style = None
        self.params: dict[str, Param] = {}

    def got_type(self, type_: str, type_r: Jinjatype) -> None:
        if self.param_name is None:
            return
        if self.param_name not in self.params:
            self.params[self.param_name] = Param()
        self.params[self.param_name].type_ = type_
        self.params[self.param_name].type_r = type_r
        self.indent = None
        self.param_name = None
        self.empty = False
        self.list_style = None
        self.state = State.COMMENT_PARAM


ctx_t = Context


def err(ctx: ctx_t, msg: str) -> None:
    print(
        "ERROR({}:{}:{}): {}\n{}".format(
            ctx.file,
            ctx.lineno,
            ctx.state,
            msg,
            ctx.line,
        ),
        file=sys.stderr,
    )


def is_comment_param(ctx: ctx_t) -> bool:
    if ctx.line.startswith(":param ") or ctx.line.startswith(":parameter "):
        ctx.state = State.COMMENT_PARAM
        return True
    return False


def is_comment_type(ctx: ctx_t) -> bool:
    if ctx.line.startswith(":type "):
        ctx.state = State.COMMENT_TYPE
        return True
    return False


def is_empty(ctx: ctx_t) -> bool:
    if ctx.line == "":
        if ctx.empty:
            err(ctx, "more than one empty line")
        ctx.empty = True
        return True
    ctx.empty = False
    return False


def is_macro(ctx: ctx_t) -> bool:
    m = re.match(r"^\{\{%-? macro ", ctx.line)
    if m:
        return True
    return False


def is_endmacro(ctx: ctx_t) -> bool:
    m = re.match(r"^\{\{%-?\s+endmacro\s+-?%\}\}$", ctx.line)
    if not m:
        return False

    for param, pp in ctx.params.items():
        if pp.seen_in_body and pp.seen_in_def and pp.seen_in_doc:
            continue
        # Jinja special variables
        if (
            param not in ("varargs", "kwargs", "caller")
            and pp.seen_in_doc
            and not pp.seen_in_def
        ):
            err(ctx, "param mismatch doc but no def '{}' {}".format(param, pp))
        elif pp.seen_in_def and not pp.seen_in_body:
            err(ctx, "param mismatch def but not in body '{}' {}".format(param, pp))
        elif not pp.seen_in_doc:
            if ctx.args.level >= 3:
                err(ctx, "param undocumented '{}' {}".format(param, pp))

    if ctx.args.log:
        print(ctx)

    ctx.clean()
    return True


def parse_pre_comment(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_macro(ctx):
        ctx.state = State.MACRO_DEF
        return parse(ctx)

    m = re.match(r"^\{\{\#-?(.*)", ctx.line)
    if not m:
        return True

    if ctx.line.endswith("#}}"):
        ctx.state = State.MACRO_DEF
        return True

    if m.group(1) != "":
        err(ctx, "Macro doc should not be at {{# line")
        return False

    ctx.state = State.COMMENT_TEXT
    return True


def parse_comment_param(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_empty(ctx):
        ctx.state = State.COMMENT_END
        return True

    if is_comment_type(ctx):
        ctx.indent = None
        return parse(ctx)

    if ctx.param_name is None:
        m = re.match(r"^:param(?:eter)?(\s+)(\w+):(.*)", ctx.line)
        if not m:
            err(ctx, "parse error header")
            return False
        delim, name, desc = m.groups()
        if delim != " ":
            err(ctx, ":param follow only one space '{}'".format(delim))
        if name in ctx.params:
            err(ctx, "{} already known {}".format(name, ctx.params.keys()))
            return False
        ctx.param_name = name
        ctx.params[name] = Param(desc=[desc], seen_in_doc=True)
        ctx.indent = ""
        return True

    m = re.match(r"^(\s*)(.*)", ctx.line)
    if not m:
        err(ctx, "continuation Parse error")
        return False

    indent, desc = m.groups()

    if ctx.indent is None:
        if indent == "":
            ctx.params[ctx.param_name].desc.append(desc)
            return True
        err(ctx, "parse_error, bad indent '{}'".format(indent))
        return False

    if ctx.indent == indent:
        ctx.params[ctx.param_name].desc.append(desc)
        return True

    if ctx.indent == "" and indent != "":
        ctx.indent = indent
        return True

    err(ctx, "parse_error '{}' != '{}'".format(ctx.indent, indent))
    return False


def parse_type(type_: str) -> tuple[bool, Jinjatype]:
    type_ = type_.strip()
    parts = re.split(r"\s*([|,\[\]])\s*", type_)

    pp = []
    for p in parts:
        if p == "":
            continue
        pp.append(p)
    parts = pp

    return _eat_types(parts, 0)


def _eat_types(parts: list[str], idx: int, is_or=False) -> tuple[bool, Jinjatype]:
    if len(parts) == 1 and parts[0] in KNOWN_TYPES:
        return True, JinjatypeSimple(parts[0])

    # print(f"_eat_types: {parts} {idx}")
    if idx >= len(parts):
        return False, Jinjatype("")

    ret: list[Jinjatype] = []

    while idx < len(parts):
        if parts[idx] == "|":
            return False, Jinjatype("")

        if parts[idx] in KNOWN_TYPES:
            # print(f"_eat_types: {parts} {idx} known")
            ret.append(JinjatypeSimple(parts[0]))
            idx += 1

        elif parts[idx] == "list":
            # print(f"_eat_types: {parts} {idx} list")
            idx += 1
            if idx >= len(parts):
                return False, Jinjatype("")
            if parts[idx] != "[":
                return False, Jinjatype("")
            idx += 1
            depth = 0
            subparts: list[str] = []
            while idx < len(parts):
                if depth == 0:
                    if parts[idx] == ",":
                        return False, Jinjatype("")
                    if parts[idx] == "]":
                        rc, jt = _eat_types(subparts, 0)
                        if rc:
                            ret.append(JinjatypeList("list[{}]".format(jt), jt))
                        else:
                            return False, Jinjatype("")
                        idx += 1
                        break
                if parts[idx] == "]":
                    depth -= 1
                if parts[idx] == "[":
                    depth += 1
                subparts.append(parts[idx])
                idx += 1
            else:
                return False, Jinjatype("")

        elif parts[idx] == "dict":
            # print(f"_eat_types: {parts} {idx} dict")
            idx += 1
            if idx >= len(parts):
                return False, Jinjatype("")
            if parts[idx] != "[":
                return False, Jinjatype("")
            idx += 1
            depth = 0
            comma = 0
            subparts = []
            while idx < len(parts):
                if depth == 0:
                    if parts[idx] == ",":
                        if comma == 0:
                            rc, jt1 = _eat_types(subparts, 0)
                            if not rc:
                                return False, Jinjatype("")
                            idx += 1
                            comma = 1
                            subparts = []
                            continue
                        return False, Jinjatype("")
                    if parts[idx] == "]":
                        if comma == 1:
                            rc, jt2 = _eat_types(subparts, 0)
                            if not rc:
                                return False, Jinjatype("")
                            idx += 1
                            break
                        return False, Jinjatype("")
                if parts[idx] == "]":
                    depth -= 1
                if parts[idx] == "[":
                    depth += 1
                subparts.append(parts[idx])
                idx += 1
            else:
                return False, Jinjatype("")
            ret.append(JinjatypeDict("dict[{}, {}]".format(jt1, jt2), jt1, jt2))

        if idx < len(parts):
            if parts[idx] != "|":
                return False, Jinjatype("")
            idx += 1

    if len(ret) == 1:
        return True, ret[0]

    return True, JinjatypeOr("", ret)


def parse_comment_type(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if not is_comment_type(ctx):
        err(ctx, "is_comment_type")
        return False

    m = re.match(r"^:type(\s+)(\w+):\s+(.*?)\s*$", ctx.line)
    if not m:
        err(ctx, "type: parse error")
        return False

    delim, name, type_ = m.groups()

    if delim != " ":
        err(ctx, ":type follow only one space")

    if ctx.param_name is None:
        err(ctx, "type without param")
        return False

    if ctx.param_name != name:
        err(
            ctx,
            ":type param name does not match param {} != {}".format(
                ctx.param_name,
                name,
            ),
        )

    rc, type_r = parse_type(type_)
    if not rc:
        err(ctx, "type name unkown {}".format(type_))

    # print(type_, type_r)
    #print(type_r)
    #jinja_out = type_r.out(name)
    #print("\n".join(jinja_out), "\n")

    if name not in ctx.params:
        err(ctx, "type name unknown {}".format(name))

    ctx.got_type(type_, type_r)
    return True


def parse_comment_end(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_empty(ctx):
        return True

    m = re.match(r"^-?#}}$", ctx.line)
    if m:
        ctx.state = State.MACRO_DEF
        return True

    err(ctx, "expected comment end #}}")
    return False


def parse_comment_list(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_empty(ctx):
        ctx.list_style = None
        ctx.state = State.COMMENT_TEXT
        return True

    m = re.match(r"^(\s*)(.*)", ctx.line)
    if not m:
        err(ctx, "Parse error")
        return False

    indent, content = m.groups()

    if ctx.indent is None:
        err(ctx, "Unexpected state indent")
        return False

    if ctx.list_style is None:
        err(ctx, "Unexpected state list_style")
        return False

    if ctx.indent != indent:
        if len(ctx.indent) > len(indent):
            err(ctx, "Unexpected shorter indent")
            return False
        return True

    ml = re.match(r"^(#\.|\d+\.|\*) ", content)
    if not ml:
        err(ctx, "Unexpected line type")
        return False

    list_style = ml.group(1)

    if ctx.list_style == list_style:
        return True

    d0 = re.match(r"^(\d+)\. ", ctx.list_style)
    d1 = re.match(r"^(\d+)\. ", list_style)

    if not d0:
        err(
            ctx, "Unexpected list style '{}' != '{}'".format(ctx.list_style, list_style)
        )
        return False

    if not d1:
        err(
            ctx, "Unexpected list style '{}' != '{}'".format(ctx.list_style, list_style)
        )
        return False

    if int(d0.group(1)) + 1 == int(d1.group(1)):
        return True

    err(ctx, "Unexpected list style '{}' != '{}'".format(ctx.list_style, list_style))
    return False


def parse_comment_cmd(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_empty(ctx):
        return True

    m = re.match(r"^(\s*)(.*)", ctx.line)
    if not m:
        err(ctx, "Parse error")
        return False

    indent, content = m.groups()
    if ctx.indent is None:
        err(ctx, "bad indent")
        return False

    if indent == "":
        ctx.state = State.COMMENT_TEXT
        return parse(ctx)

    if len(ctx.indent) >= len(indent):
        ctx.state = State.COMMENT_TEXT
        return parse(ctx)

    return True


def parse_comment_text(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_empty(ctx):
        return True

    m = re.match(r"^-?#}}$", ctx.line)
    if m:
        ctx.state = State.MACRO_DEF
        return True

    m = re.match(r"^(\s*)(.*)", ctx.line)
    if not m:
        err(ctx, "Parse error")
        return False

    indent, content = m.groups()

    if indent == "":
        if is_comment_param(ctx):
            return parse(ctx)

        if is_comment_type(ctx):
            err(ctx, "Unexpected type")
            return False

    ctx.indent = indent

    if ctx.line.endswith("::"):
        ctx.state = State.COMMENT_CMD

    if content.startswith((":param", ":type")):
        err(ctx, ":param or :type indented bad")
    mc = re.match(r"[$>>{}]|\w+\(|\{\{|\}\}", content)
    if mc:
        err(ctx, "seem like command but not started with ::")
        return False
    ml = re.match(r"^(#\.|\d+\.|\*) ", content)
    if ml:
        line_style = ml.group(1)
        ctx.list_style = line_style
        ctx.state = State.COMMENT_LIST
        return parse(ctx)

    return True


def parse_macro_def(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return False

    if is_empty(ctx):
        ctx.state = State.PRE_COMMENT
        return True

    m = re.match(r"^\{\{%-? set \w+ = .*? -?%}}$", ctx.line)
    if m:
        ctx.state = State.PRE_COMMENT
        return True

    m = re.match(r"^\{\{%-? macro (\w+)\(\s*(.*?)\s*\) -?%\}\}$", ctx.line)
    if not m:
        err(ctx, "parse def error")
        return False

    ctx.macro_name, params_raw_str = m.groups()
    if params_raw_str == "":
        ctx.state = State.MACRO_BODY
        return True

    params_raw = re.split(r"(\s*,\s*)", params_raw_str)
    st = "param"
    params: list[tuple[str, str | None]] = []
    for param in params_raw:
        param = param.strip()
        if st == "param":
            m = re.match(r"^\w+$", param)
            if m:
                params.append((param, None, None))
                st = "comma"
                continue
            m = re.match(r"^(\w+)=(['\"])(.*)\2$", param)
            if m:
                param_name, _, param_default = m.groups()
                params.append((param_name, param_default, "str"))
                st = "comma"
                continue
            m = re.match(
                r"^(\w+)=(False|false|True|true|None|none|\d+|\[\]|\{\})$", param
            )
            if m:
                param_name, param_default = m.groups()
                t_ = m.group(1)
                type_ = None
                if t_ in ("False", "false", "True", "true"):
                    type_ = "bool"
                elif t_ in ("None", "none"):
                    pass
                elif t_ == "[]":
                    type_ = "list"
                elif t_ == "{}":
                    type_ = "dict"
                elif re.match(r"^\d+$", t_):
                    type_ = "int"
                params.append((param_name, param_default, type_))
                st = "comma"
                continue
            err(ctx, "param parse error '{}'".format(param))
            return False
        if st == "comma":
            if param == ",":
                st = "param"
                continue
            err(ctx, "param comma error '{}'".format(param))
            return False

    ctx.state = State.MACRO_BODY
    for name, default, type_ in params:
        if name in ctx.params:
            pp = ctx.params[name]
            pp.default = default
            pp.seen_in_def = True
            if type_ is not None and pp.type_ is not None:
                if pp.type_ == "char" and type_ == "str":
                    pass
                elif pp.type_ != type_:
                    err(ctx, "type mismatch '{}' != '{}'".format(pp.type_, type_))
                    return False
            elif pp.type_ is None:
                pp.type_ = type_
        else:
            ctx.params[name] = Param(seen_in_def=True, default=default, type_=type_)
    return True


def parse_macro_body(ctx: ctx_t) -> bool:
    if is_endmacro(ctx):
        return True

    if is_macro(ctx):
        err(ctx, "parse error macro")
        return False

    vals_raw = re.findall(r"\{\{\{-?\s*(.*?)\s*-?\}\}\}", ctx.line)
    for val_raw in vals_raw:
        vals = re.findall(r"(\w+)", val_raw)
        for val in vals:
            if val in ctx.params:
                ctx.params[val].seen_in_body = True

    bools = re.findall(r"\{\{%-?\s+(?:el)?if\s+(?:not\s+)?(\w+)\s+-?%}}", ctx.line)
    for b in bools:
        if b in ctx.params:
            if ctx.params[b].type_ is None:
                ctx.params[b].type_ = "bool"
            elif ctx.params[b].type_ != "bool":
                if ctx.args.level >= 2:
                    err(ctx, "maybe bool {}".format(b))

    vals_raw = re.findall(r"\{\{\%-?\s*(.*?)\s*-?\%\}\}", ctx.line)
    for val_raw in vals_raw:
        vals = re.findall(r"(\w+)", val_raw)
        for val in vals:
            if val in ctx.params:
                ctx.params[val].seen_in_body = True

    line = re.sub(r"\{\{\{.*?}}}", "", ctx.line)
    m = re.match(r"\{\{\{", line)
    if m:
        ctx.state = State.MACRO_BODY_STATEMENT
        return parse(ctx)

    line = re.sub(r"\{\{%.*?%}}", "", ctx.line)
    m = re.match(r"(?:\{\{%.*?}}}.*?)*\{\{%", line)
    if m:
        ctx.state = State.MACRO_BODY_EXPRESSION
        return parse(ctx)

    return True


def parse_macro_body_expression(ctx: ctx_t) -> bool:
    line = ctx.line
    m = re.match(r"^.*%}}.*?\{\{%-?\s*(.*?)$", line)
    if m:
        line = m.group(1)
    else:
        m = re.match(r"^(.*?)\s*-?%}}", line)
        if m:
            line = m.group(1)
            ctx.state = State.MACRO_BODY

    vals = re.findall(r"(\w+)", line)
    for val in vals:
        if val in ctx.params:
            ctx.params[val].seen_in_body = True

    return True


def parse_macro_body_statement(ctx: ctx_t) -> bool:
    line = ctx.line
    m = re.match(r"^.*}}}.*?\{\{\{-?\s*(.*?)$", line)
    if m:
        line = m.group(1)
    else:
        m = re.match(r"^(.*?)\s*-?}}}", line)
        if m:
            line = m.group(1)
            ctx.state = State.MACRO_BODY

    vals = re.findall(r"(\w+)", line)
    for val in vals:
        if val in ctx.params:
            ctx.params[val].seen_in_body = True

    return True


def parse(ctx: ctx_t) -> bool:
    if ctx.args.log:
        print("{}:{} {} {}".format(ctx.file, ctx.lineno, ctx.state, ctx.line))
    if ctx.state == State.PRE_COMMENT:
        return parse_pre_comment(ctx)
    if ctx.state == State.COMMENT_TEXT:
        return parse_comment_text(ctx)
    if ctx.state == State.COMMENT_PARAM:
        return parse_comment_param(ctx)
    if ctx.state == State.COMMENT_TYPE:
        return parse_comment_type(ctx)
    if ctx.state == State.COMMENT_CMD:
        return parse_comment_cmd(ctx)
    if ctx.state == State.COMMENT_END:
        return parse_comment_end(ctx)
    if ctx.state == State.COMMENT_LIST:
        return parse_comment_list(ctx)
    if ctx.state == State.MACRO_DEF:
        return parse_macro_def(ctx)
    if ctx.state == State.MACRO_BODY:
        return parse_macro_body(ctx)
    if ctx.state == State.MACRO_BODY_EXPRESSION:
        return parse_macro_body_expression(ctx)
    if ctx.state == State.MACRO_BODY_STATEMENT:
        return parse_macro_body_statement(ctx)

    err(ctx, "Parse error")
    return False


def check_file(file: str, args: argparse.Namespace) -> None:
    with open(file) as fd:
        ctx = Context(file, args)
        for line in fd:
            ctx.lineno += 1
            ctx.line = line.rstrip()
            ok = parse(ctx)
            if not ok:
                sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", nargs="+")
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--level", default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for file in args.file:
        check_file(file, args)


if __name__ == "__main__":
    main()
