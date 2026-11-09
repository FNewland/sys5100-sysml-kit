// SysMLCheck: thin command-line wrapper around the OMG SysML v2 Pilot Implementation
// (org.omg.sysml.interactive.SysMLInteractive, EPL-2.0).
//
//   java -cp jupyter-sysml-kernel-<ver>-all.jar:build SysMLCheck \
//        --lib <sysml.library dir> [--pre lib.sysml ...] [--json facts.json | --batch outdir]
//        [--viz out.svg=QName[@VIEW] ...] [--max-issues N] file1.sysml [file2.sysml ...]
//
// --pre    files processed first (e.g. the course library); their issues are reported too.
// --json   all model files form ONE model; one facts JSON.
// --batch  each model file is a SEPARATE model; writes <outdir>/<basename>.json per file
//          (library loaded once; used by the kit's tests and for marking many models).
// (SYS 5100 sysml-kit version; adapted from the Oct 2026 prototype.)
//
// 1. Parses and validates each file against the standard library (syntax + semantic errors).
// 2. Optionally writes a compact "facts" JSON (requirements, satisfy/verify links, part tree
//    with attribute values, ports, interfaces, states, transitions) for Python CI checks.
// 3. Optionally emits PlantUML text for a diagram of one element (the %viz engine).
// Exit code: 0 = no errors, 1 = errors, 2 = usage/IO failure.

import java.nio.file.*;
import java.util.*;
import org.eclipse.emf.ecore.EObject;
import org.eclipse.xtext.nodemodel.ICompositeNode;
import org.eclipse.xtext.nodemodel.util.NodeModelUtils;
import org.eclipse.xtext.validation.Issue;
import org.omg.sysml.interactive.SysMLInteractive;
import org.omg.sysml.interactive.SysMLInteractiveResult;
import org.omg.sysml.lang.sysml.*;
import org.omg.sysml.util.EvaluationUtil;
import org.omg.sysml.util.FeatureUtil;

public class SysMLCheck {

    // ---------------- tiny JSON writer ----------------
    static String q(String s) {
        if (s == null) return "null";
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray()) {
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': break;
                case '\t': b.append("\\t"); break;
                default: if (c < 0x20) b.append(String.format("\\u%04x", (int) c)); else b.append(c);
            }
        }
        return b.append('"').toString();
    }
    static String arr(Collection<String> xs) { return "[" + String.join(",", xs) + "]"; }
    static String obj(Map<String, String> m) {
        List<String> parts = new ArrayList<>();
        m.forEach((k, v) -> parts.add(q(k) + ":" + v));
        return "{" + String.join(",", parts) + "}";
    }

    // ---------------- helpers ----------------
    static String text(EObject e) {
        ICompositeNode n = NodeModelUtils.findActualNodeFor(e);
        return n == null ? null : NodeModelUtils.getTokenText(n);
    }
    static int line(EObject e) {
        ICompositeNode n = NodeModelUtils.findActualNodeFor(e);
        return n == null ? -1 : n.getStartLine();
    }
    /** Dotted path for a feature reference, following feature chains (a.b.c). */
    static String path(Feature f) {
        if (f == null) return null;
        if (!f.getChainingFeature().isEmpty()) {
            List<String> ns = new ArrayList<>();
            for (Feature c : f.getChainingFeature()) ns.add(c.getName());
            return String.join(".", ns);
        }
        Feature ref = FeatureUtil.getReferencedFeatureOf(f);
        if (ref != null && ref != f) return path(ref);
        return f.getQualifiedName() != null ? f.getQualifiedName() : f.getName();
    }
    static String typeNames(Feature f) {
        List<String> ts = new ArrayList<>();
        for (Type t : f.getType()) if (!t.isLibraryElement()) ts.add(q(t.getQualifiedName()));
        return arr(ts);
    }
    static String evalText(Expression ex, Element target) {
        try {
            List<Element> r = EvaluationUtil.evaluate(ex, target);
            if (r == null) return null;
            List<String> vs = new ArrayList<>();
            for (Element e : r) {
                Object v = (e instanceof LiteralExpression) ? EvaluationUtil.valueOf(e) : null;
                if (v == null) return null;   // not reducible to a literal (e.g. quantity with unit)
                vs.add(v.toString());
            }
            return vs.isEmpty() ? null : String.join(", ", vs);
        } catch (Throwable t) {
            return "<eval failed: " + t.getClass().getSimpleName() + ">";
        }
    }
    static List<Feature> userFeatures(Type t, java.lang.Class<?> kind) {
        List<Feature> out = new ArrayList<>();
        for (Feature f : t.getFeature())
            if (kind.isInstance(f) && !f.isLibraryElement() && f.getName() != null) out.add(f);
        return out;
    }

    // ---------------- part tree ----------------
    static String partJson(Feature p, String prefix, Element evalTarget, int depth) {
        Map<String, String> m = new LinkedHashMap<>();
        String here = prefix == null ? p.getName() : prefix + "." + p.getName();
        m.put("name", q(p.getName()));
        m.put("path", q(here));
        m.put("qname", q(p.getQualifiedName()));
        m.put("types", typeNames(p));
        m.put("metadata", metaJson(p));
        m.put("line", String.valueOf(line(p)));
        List<String> attrs = new ArrayList<>();
        for (Feature a : userFeatures((Type) p, AttributeUsage.class)) {
            Map<String, String> am = new LinkedHashMap<>();
            am.put("name", q(a.getName()));
            List<String> ats = new ArrayList<>();
            for (Type t : a.getType()) ats.add(q(t.getName()));
            am.put("types", arr(ats));
            Expression ex = FeatureUtil.getValueExpressionFor(a);
            am.put("value", q(ex == null ? null : text(ex)));
            am.put("evaluated", q(ex == null ? null : evalText(ex, p)));
            am.put("evidence", q(evidenceOf(a)));
            am.put("metadata", metaJson(a));
            am.put("line", String.valueOf(line(a)));
            attrs.add(obj(am));
        }
        m.put("attributes", arr(attrs));
        List<String> ports = new ArrayList<>();
        for (Feature pt : userFeatures((Type) p, PortUsage.class)) {
            Map<String, String> pm = new LinkedHashMap<>();
            pm.put("name", q(pt.getName()));
            pm.put("path", q(here + "." + pt.getName()));
            pm.put("types", typeNames(pt));
            ports.add(obj(pm));
        }
        m.put("ports", arr(ports));
        List<String> conns = new ArrayList<>();
        for (Feature c : ((Type) p).getFeature()) {
            if (c instanceof ConnectorAsUsage && !c.isLibraryElement()) {
                Connector cn = (Connector) c;
                List<String> ends = new ArrayList<>();
                for (Feature end : cn.getConnectorEnd()) ends.add(q(path(end)));
                Map<String, String> cm = new LinkedHashMap<>();
                cm.put("name", q(c.getName()));
                cm.put("kind", q(c.eClass().getName()));
                cm.put("types", typeNames(c));
                cm.put("ends", arr(ends));
                conns.add(obj(cm));
            }
        }
        m.put("connections", arr(conns));
        List<String> kids = new ArrayList<>();
        if (depth < 6)
            for (Feature k : userFeatures((Type) p, PartUsage.class))
                if (!(k instanceof ConnectorAsUsage)) kids.add(partJson(k, here, k, depth + 1));
        m.put("parts", arr(kids));
        List<String> states = new ArrayList<>();
        for (Feature s : userFeatures((Type) p, StateUsage.class))
            if (!(s instanceof TransitionUsage)) states.add(q(path(s) + " : " + typeNames(s)));
        m.put("exhibits", arr(states));
        return obj(m);
    }

    /** Value of the first 'grade' feature in any metadata annotating this element (e.g. @Evidence). */
    static String evidenceOf(Element a) {
        for (Element o : a.getOwnedElement()) {
            if (o instanceof MetadataFeature) {
                for (Feature f : ((MetadataFeature) o).getOwnedFeature()) {
                    if ("grade".equals(f.getName()) || "basis".equals(f.getName())) {
                        Expression ex = FeatureUtil.getValueExpressionFor(f);
                        String t = ex == null ? null : text(ex);
                        if (t != null && t.contains("::")) t = t.substring(t.lastIndexOf("::") + 2);
                        return t;
                    }
                }
            }
        }
        return null;
    }

    /** Value text of a named feature in any metadata annotating this element (quotes stripped). */
    static String metaValue(Element a, String feature) {
        for (Element o : a.getOwnedElement())
            if (o instanceof MetadataFeature)
                for (Feature f : ((MetadataFeature) o).getOwnedFeature())
                    if (feature.equals(f.getName())) {
                        Expression ex = FeatureUtil.getValueExpressionFor(f);
                        String t = ex == null ? null : text(ex);
                        return t == null ? null : t.replaceAll("^\"|\"$", "");
                    }
        return null;
    }

    /** All metadata annotations on an element: [{"type": "Evidence", "values": {"grade": "Basis::assumed", ...}}]. */
    static String metaJson(Element a) {
        List<String> out = new ArrayList<>();
        for (Element o : a.getOwnedElement()) {
            if (!(o instanceof MetadataFeature)) continue;
            MetadataFeature mf = (MetadataFeature) o;
            Map<String, String> m = new LinkedHashMap<>();
            Metaclass mc = null;
            try { mc = mf.getMetaclass(); } catch (Throwable t) { /* ignore */ }
            m.put("type", q(mc == null ? null : mc.getName()));
            Map<String, String> vals = new LinkedHashMap<>();
            for (Feature f : mf.getOwnedFeature()) {
                if (f.getName() == null) {
                    // redefinitions written as 'grade = ...' are owned features whose name comes from the redefined feature
                    String nm = null;
                    for (Redefinition r : f.getOwnedRedefinition())
                        if (r.getRedefinedFeature() != null) nm = r.getRedefinedFeature().getName();
                    if (nm == null) continue;
                    Expression ex = FeatureUtil.getValueExpressionFor(f);
                    vals.put(nm, q(ex == null ? null : text(ex)));
                } else {
                    Expression ex = FeatureUtil.getValueExpressionFor(f);
                    vals.put(f.getName(), q(ex == null ? null : text(ex)));
                }
            }
            m.put("values", obj(vals));
            m.put("line", String.valueOf(line(mf)));
            out.add(obj(m));
        }
        return arr(out);
    }

    static String attrsJson(Type t) {
        List<String> attrs = new ArrayList<>();
        for (Feature a : userFeatures(t, AttributeUsage.class)) {
            Map<String, String> am = new LinkedHashMap<>();
            am.put("name", q(a.getName()));
            Expression ex = FeatureUtil.getValueExpressionFor(a);
            am.put("value", q(ex == null ? null : text(ex)));
            attrs.add(obj(am));
        }
        return arr(attrs);
    }

    static String verifierOf(Element e) {
        for (EObject o = e; o != null; o = o.eContainer())
            if (o instanceof VerificationCaseDefinition || o instanceof VerificationCaseUsage)
                return ((Element) o).getQualifiedName();
        return null;
    }

    // ---------------- facts extraction ----------------
    static String reqId(RequirementUsage r) {
        String id = r.getReqId() != null ? r.getReqId() : r.getDeclaredShortName();
        if (id == null)
            for (Type t : r.getType())
                if (t instanceof RequirementDefinition && !t.isLibraryElement()) {
                    RequirementDefinition d = (RequirementDefinition) t;
                    id = d.getReqId() != null ? d.getReqId() : d.getDeclaredShortName();
                    if (id != null) break;
                }
        return id;
    }
    static List<String> reqText(RequirementUsage r) {
        List<String> txt = new ArrayList<>();
        for (String t : r.getText()) if (t != null && !t.trim().isEmpty()) txt.add(t.trim());
        if (txt.isEmpty())
            for (Type t : r.getType())
                if (t instanceof RequirementDefinition && !t.isLibraryElement())
                    for (String x : ((RequirementDefinition) t).getText())
                        if (x != null && !x.trim().isEmpty()) txt.add(x.trim());
        return txt;
    }
    static boolean topLevel(Element e) {
        return e.getOwningNamespace() instanceof org.omg.sysml.lang.sysml.Package;
    }

    static String facts(List<Element> roots, int errors, int warnings) {
        List<String> reqs = new ArrayList<>(), reqDefs = new ArrayList<>(), sats = new ArrayList<>(),
                vers = new ArrayList<>(), parts = new ArrayList<>(), partDefs = new ArrayList<>(),
                stateDefs = new ArrayList<>(), calcs = new ArrayList<>(), concerns = new ArrayList<>(),
                vcases = new ArrayList<>(), allocs = new ArrayList<>(), ifdefs = new ArrayList<>();
        for (Element root : roots) {
            Iterator<EObject> it = root.eAllContents();
            while (it.hasNext()) {
                EObject e = it.next();
                if (e instanceof SatisfyRequirementUsage) {
                    SatisfyRequirementUsage su = (SatisfyRequirementUsage) e;
                    Map<String, String> m = new LinkedHashMap<>();
                    RequirementUsage target = su.getSatisfiedRequirement();
                    m.put("requirement", q(target == null ? null : target.getQualifiedName()));
                    m.put("by", q(path(su.getSatisfyingFeature())));
                    m.put("line", String.valueOf(line(su)));
                    sats.add(obj(m));
                } else if (e instanceof RequirementVerificationMembership) {
                    RequirementVerificationMembership vm = (RequirementVerificationMembership) e;
                    RequirementUsage target = vm.getVerifiedRequirement();
                    Feature ref = target == null ? null : FeatureUtil.getReferencedFeatureOf(target);
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("requirement", q(ref != null ? ref.getQualifiedName() : target == null ? null : target.getQualifiedName()));
                    m.put("by", q(verifierOf(vm)));
                    vers.add(obj(m));
                } else if (e instanceof ConcernUsage || e instanceof ConcernDefinition) {
                    Element c = (Element) e;
                    if (topLevel(c)) concerns.add(q(c.getQualifiedName()));
                } else if (e instanceof VerificationCaseUsage) {
                    VerificationCaseUsage v = (VerificationCaseUsage) e;
                    if (!topLevel(v)) continue;
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("qname", q(v.getQualifiedName()));
                    m.put("name", q(v.getName()));
                    m.put("types", typeNames(v));
                    Usage subj = null;
                    for (Feature f : v.getOwnedFeature())
                        if (f instanceof ReferenceUsage && f.getName() != null && f.getOwningMembership() instanceof SubjectMembership) subj = (Usage) f;
                    String subjVal = null;
                    if (subj != null) { Expression ex = FeatureUtil.getValueExpressionFor(subj); subjVal = ex == null ? null : text(ex); }
                    m.put("subject", q(subjVal));
                    List<String> docs = new ArrayList<>();
                    for (Type t : v.getType()) if (!t.isLibraryElement()) for (Documentation d : t.getDocumentation()) docs.add(q(d.getBody().trim()));
                    for (Documentation d : v.getDocumentation()) docs.add(q(d.getBody().trim()));
                    m.put("doc", arr(docs));
                    m.put("metadata", metaJson(v));
                    m.put("line", String.valueOf(line(v)));
                    vcases.add(obj(m));
                } else if (e instanceof AllocationUsage) {
                    AllocationUsage a = (AllocationUsage) e;
                    List<String> ends = new ArrayList<>();
                    for (Feature end : a.getConnectorEnd()) ends.add(q(path(end)));
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("name", q(a.getName()));
                    m.put("ends", arr(ends));
                    m.put("line", String.valueOf(line(a)));
                    allocs.add(obj(m));
                } else if (e instanceof InterfaceDefinition) {
                    InterfaceDefinition d = (InterfaceDefinition) e;
                    List<String> ends = new ArrayList<>();
                    for (Feature end : d.getOwnedFeature()) {
                        if (!end.isEnd()) continue;
                        Map<String, String> em = new LinkedHashMap<>();
                        em.put("name", q(end.getName()));
                        em.put("types", typeNames(end));
                        em.put("text", q(text(end)));
                        ends.add(obj(em));
                    }
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("qname", q(d.getQualifiedName()));
                    m.put("ends", arr(ends));
                    m.put("line", String.valueOf(line(d)));
                    ifdefs.add(obj(m));
                } else if (e instanceof RequirementUsage) {
                    RequirementUsage r = (RequirementUsage) e;
                    if (!topLevel(r)) continue;
                    if (r instanceof SatisfyRequirementUsage) continue;
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("qname", q(r.getQualifiedName()));
                    m.put("name", q(r.getName()));
                    m.put("id", q(reqId(r)));
                    List<String> txt = new ArrayList<>();
                    for (String t : reqText(r)) txt.add(q(t));
                    m.put("text", arr(txt));
                    m.put("types", typeNames(r));
                    List<String> fr = new ArrayList<>();
                    for (ConcernUsage c : r.getFramedConcern()) fr.add(q(path(c)));
                    m.put("frames", arr(fr));
                    List<String> cs = new ArrayList<>();
                    for (ConstraintUsage c : r.getRequiredConstraint()) {
                        Expression res = EvaluationUtil.getResultExpressionFor(c);
                        String t = res != null ? text(res) : null;
                        if (t != null && !c.isLibraryElement()) cs.add(q(t.trim()));
                    }
                    m.put("constraints", arr(cs));
                    Usage subj = r.getSubjectParameter();
                    m.put("subject", q(subj == null ? null : subj.getName()));
                    m.put("subjectTypes", subj == null ? "[]" : typeNames(subj));
                    m.put("attributes", attrsJson(r));
                    m.put("metadata", metaJson(r));
                    m.put("line", String.valueOf(line(r)));
                    reqs.add(obj(m));
                } else if (e instanceof RequirementDefinition) {
                    RequirementDefinition r = (RequirementDefinition) e;
                    if (r instanceof ConcernDefinition) continue;
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("qname", q(r.getQualifiedName()));
                    m.put("id", q(r.getReqId()));
                    reqDefs.add(obj(m));
                } else if (e instanceof PartUsage && !(e instanceof ConnectorAsUsage)) {
                    PartUsage p = (PartUsage) e;
                    if (topLevel(p)) parts.add(partJson(p, null, p, 0));
                } else if (e instanceof PartDefinition) {
                    PartDefinition d = (PartDefinition) e;
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("qname", q(d.getQualifiedName()));
                    List<String> ps = new ArrayList<>();
                    for (Feature pt : userFeatures(d, PortUsage.class)) ps.add(q(pt.getName()));
                    m.put("ports", arr(ps));
                    partDefs.add(obj(m));
                } else if (e instanceof StateDefinition) {
                    StateDefinition sd = (StateDefinition) e;
                    Map<String, String> m = new LinkedHashMap<>();
                    m.put("qname", q(sd.getQualifiedName()));
                    List<String> st = new ArrayList<>();
                    for (Feature su : sd.getOwnedFeature())
                        if (su instanceof StateUsage && !(su instanceof TransitionUsage)) st.add(q(su.getName()));
                    m.put("states", arr(st));
                    List<String> tr = new ArrayList<>();
                    for (Feature f : sd.getOwnedFeature()) {
                        if (f instanceof TransitionUsage) {
                            TransitionUsage tu = (TransitionUsage) f;
                            Map<String, String> tm = new LinkedHashMap<>();
                            tm.put("name", q(tu.getName()));
                            tm.put("source", q(tu.getSource() == null ? null : tu.getSource().getName()));
                            tm.put("target", q(tu.getTarget() == null ? null : tu.getTarget().getName()));
                            List<String> trig = new ArrayList<>();
                            for (AcceptActionUsage a : tu.getTriggerAction()) trig.add(q(text(a)));
                            tm.put("triggers", arr(trig));
                            tr.add(obj(tm));
                        } else if (f instanceof SuccessionAsUsage) {
                            Succession sc = (Succession) f;
                            List<Feature> rel = sc.getRelatedFeature();
                            if (rel.size() == 2) {
                                Map<String, String> tm = new LinkedHashMap<>();
                                Feature src = rel.get(0), tgt = rel.get(1);
                                tm.put("name", q("initial"));
                                tm.put("source", q(src == sd.getEntryAction() ? "entry" : src.getName()));
                                tm.put("target", q(tgt.getName()));
                                tm.put("triggers", "[]");
                                tr.add(obj(tm));
                            }
                        }
                    }
                    m.put("transitions", arr(tr));
                    m.put("line", String.valueOf(line(sd)));
                    stateDefs.add(obj(m));
                } else if (e instanceof CalculationDefinition || e instanceof CalculationUsage) {
                    Element c = (Element) e;
                    if (topLevel(c)) calcs.add(q(c.eClass().getName() + " " + c.getQualifiedName()));
                }
            }
        }
        Map<String, String> out = new LinkedHashMap<>();
        out.put("tool", q("SysML v2 Pilot Implementation via SysMLCheck.java"));
        out.put("errors", String.valueOf(errors));
        out.put("warnings", String.valueOf(warnings));
        out.put("concerns", arr(concerns));
        out.put("requirements", arr(reqs));
        out.put("requirementDefs", arr(reqDefs));
        out.put("satisfy", arr(sats));
        out.put("verify", arr(vers));
        out.put("verifications", arr(vcases));
        out.put("allocations", arr(allocs));
        out.put("interfaceDefs", arr(ifdefs));
        out.put("partDefs", arr(partDefs));
        out.put("parts", arr(parts));
        out.put("stateDefs", arr(stateDefs));
        out.put("calcs", arr(calcs));
        return obj(out);
    }

    /** Process one file; print its issues; return {errors, warnings}. */
    static int[] processFile(SysMLInteractive s, String f, List<Element> roots, int maxIssues) throws Exception {
        String src = Files.readString(Path.of(f));
        SysMLInteractiveResult r = s.process(src);
        int errors = 0, warnings = 0;
        if (r.getException() != null) {
            System.out.println(f + ":1:1: ERROR: " + r.formatException().split("\n")[0]);
            return new int[]{1, 0};
        }
        // Syntax errors first: one slip (e.g. a missing ';') cascades into dozens of
        // "Couldn't resolve reference" errors, so students should fix the first one and re-run.
        List<Issue> ordered = new ArrayList<>(r.getSyntaxErrors());
        for (Issue is : r.getIssues()) if (!ordered.contains(is)) ordered.add(is);
        int shown = 0;
        for (Issue is : ordered) {
            String sev = is.getSeverity().toString();
            if (sev.equals("ERROR")) errors++; else if (sev.equals("WARNING")) warnings++; else continue;
            if (shown++ < maxIssues)
                System.out.printf("%s:%d:%d: %s: %s%n", f, is.getLineNumber(), is.getColumn(), sev,
                        String.valueOf(is.getMessage()).replace('\n', ' '));
        }
        if (r.getRootElement() != null && roots != null) roots.add(r.getRootElement());
        System.out.printf("FILE %s errors=%d warnings=%d%n", f, errors, warnings);
        return new int[]{errors, warnings};
    }

    public static void main(String[] args) throws Exception {
        int maxIssues = 10000; String lib = null, json = null, batch = null;
        List<String> files = new ArrayList<>(), pre = new ArrayList<>(), viz = new ArrayList<>();
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--lib": lib = args[++i]; break;
                case "--json": json = args[++i]; break;
                case "--batch": batch = args[++i]; break;
                case "--pre": pre.add(args[++i]); break;
                case "--viz": viz.add(args[++i]); break;
                case "--max-issues": maxIssues = Integer.parseInt(args[++i]); break;
                default: files.add(args[i]);
            }
        }
        if (lib == null || files.isEmpty()) {
            System.err.println("usage: SysMLCheck --lib <sysml.library> [--pre lib.sysml] [--json out | --batch dir] [--viz out.svg=QName[@VIEW]] file...");
            System.exit(2);
        }
        long t0 = System.currentTimeMillis();
        SysMLInteractive s = SysMLInteractive.createInstance();
        s.loadLibrary(lib.endsWith("/") ? lib : lib + "/");
        long t1 = System.currentTimeMillis();
        System.err.printf("library loaded in %.1f s%n", (t1 - t0) / 1000.0);

        int preErrors = 0;
        for (String f : pre) preErrors += processFile(s, f, null, maxIssues)[0];

        int exit = preErrors > 0 ? 1 : 0;
        if (batch != null) {
            Files.createDirectories(Path.of(batch));
            for (String f : files) {
                List<Element> roots = new ArrayList<>();
                int[] ew = processFile(s, f, roots, maxIssues);
                String base = Path.of(f).getFileName().toString().replaceAll("\\.sysml$", "");
                Files.writeString(Path.of(batch, base + ".json"), facts(roots, ew[0] + preErrors, ew[1]));
                if (ew[0] > 0) exit = 1;
                s.removeResource();   // keep models independent of each other
            }
        } else {
            int errors = preErrors, warnings = 0;
            List<Element> roots = new ArrayList<>();
            for (String f : files) {
                int[] ew = processFile(s, f, roots, maxIssues);
                errors += ew[0]; warnings += ew[1];
            }
            System.out.printf("parsed %d file(s): %d error(s), %d warning(s) in %.1f s%n",
                    files.size(), errors, warnings, (System.currentTimeMillis() - t1) / 1000.0);
            if (json != null) {
                Files.writeString(Path.of(json), facts(roots, errors, warnings));
                System.err.println("facts written to " + json);
            }
            for (String spec : viz) {
                // out.svg=Qualified::Name[@VIEW]
                int eq = spec.indexOf('=');
                String out = spec.substring(0, eq), target = spec.substring(eq + 1), view = null;
                int at = target.indexOf('@');
                if (at > 0) { view = target.substring(at + 1); target = target.substring(0, at); }
                try {
                    s.setGraphVizPath(System.getenv().getOrDefault("GRAPHVIZ_DOT", "/usr/bin/dot"));
                    org.omg.sysml.interactive.VizResult v = s.viz(List.of(target), view == null ? List.of() : List.of(view), List.of(), List.of());
                    if (v.hasException()) { System.err.println("viz: " + target + ": " + v.formatException().split("\n")[0]); continue; }
                    String body = v.getSVG() != null ? v.getSVG() : v.getPlantUML() != null ? v.getPlantUML() : v.getText();
                    Files.writeString(Path.of(out), String.valueOf(body));
                    System.err.println("diagram written to " + out);
                } catch (Throwable t) {
                    System.err.println("viz failed: " + target + ": " + t);
                }
            }
            if (errors > 0) exit = 1;
        }
        System.exit(exit);
    }
}
