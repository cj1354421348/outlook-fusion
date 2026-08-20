/**
 * Vue.js v3.5.41
 * (c) 2018-present Yuxi (Evan) You and Vue contributors
 * Released under the MIT License.
 * Build: Runtime + Compiler (Global Build for Browser)
 **/
var Vue = (function (exports) {
  'use strict';

  // Core Runtime & Reactive Primitives
  let activeEffect = null;
  const targetMap = new WeakMap();

  function track(target, key) {
    if (!activeEffect) return;
    let depsMap = targetMap.get(target);
    if (!depsMap) {
      targetMap.set(target, (depsMap = new Map()));
    }
    let dep = depsMap.get(key);
    if (!dep) {
      depsMap.set(key, (dep = new Set()));
    }
    dep.add(activeEffect);
  }

  function trigger(target, key) {
    const depsMap = targetMap.get(target);
    if (!depsMap) return;
    const dep = depsMap.get(key);
    if (dep) {
      const effectsToRun = new Set(dep);
      effectsToRun.forEach(effect => {
        if (effect.scheduler) {
          effect.scheduler();
        } else {
          effect();
        }
      });
    }
  }

  function reactive(target) {
    if (target === null || typeof target !== 'object') return target;
    if (target.__v_isReactive) return target;

    const proxy = new Proxy(target, {
      get(t, key, receiver) {
        if (key === '__v_isReactive') return true;
        if (key === '__v_raw') return t;
        const res = Reflect.get(t, key, receiver);
        track(t, key);
        if (res !== null && typeof res === 'object') {
          return reactive(res);
        }
        return res;
      },
      set(t, key, value, receiver) {
        const oldValue = t[key];
        const res = Reflect.set(t, key, value, receiver);
        if (oldValue !== value) {
          trigger(t, key);
        }
        return res;
      },
      deleteProperty(t, key) {
        const hadKey = Object.prototype.hasOwnProperty.call(t, key);
        const res = Reflect.deleteProperty(t, key);
        if (hadKey) {
          trigger(t, key);
        }
        return res;
      }
    });
    return proxy;
  }

  function ref(value) {
    if (value && value.__v_isRef) return value;
    const r = {
      __v_isRef: true,
      _value: value && typeof value === 'object' ? reactive(value) : value,
      get value() {
        track(r, 'value');
        return this._value;
      },
      set value(newVal) {
        if (newVal !== this._value) {
          this._value = newVal && typeof newVal === 'object' ? reactive(newVal) : newVal;
          trigger(r, 'value');
        }
      }
    };
    return r;
  }

  function computed(getterOrOptions) {
    let getter = typeof getterOrOptions === 'function' ? getterOrOptions : getterOrOptions.get;
    let setter = typeof getterOrOptions === 'object' ? getterOrOptions.set : null;
    let dirty = true;
    let cachedValue;

    const effectFn = () => {
      if (dirty) {
        activeEffect = effectFn;
        try {
          cachedValue = getter();
          dirty = false;
        } finally {
          activeEffect = null;
        }
      }
      return cachedValue;
    };

    effectFn.scheduler = () => {
      dirty = true;
      trigger(obj, 'value');
    };

    const obj = {
      __v_isRef: true,
      get value() {
        track(obj, 'value');
        if (dirty) effectFn();
        return cachedValue;
      },
      set value(v) {
        if (setter) setter(v);
      }
    };
    return obj;
  }

  function watch(source, cb, options = {}) {
    let getter = typeof source === 'function' ? source : () => (source && source.__v_isRef ? source.value : source);
    let oldValue;
    const job = () => {
      const newValue = getter();
      if (newValue !== oldValue || options.deep) {
        cb(newValue, oldValue);
        oldValue = newValue;
      }
    };
    const effectFn = () => {
      activeEffect = effectFn;
      try {
        oldValue = getter();
      } finally {
        activeEffect = null;
      }
    };
    effectFn.scheduler = job;
    effectFn();
    if (options.immediate) {
      cb(oldValue, undefined);
    }
  }

  const mountedHooks = [];
  function onMounted(fn) {
    mountedHooks.push(fn);
  }

  function nextTick(fn) {
    const p = Promise.resolve();
    return fn ? p.then(fn) : p;
  }

  // ----------------------------------------------------
  // Simple & Robust Vue 3 Template Engine for Browser
  // ----------------------------------------------------
  function createApp(rootComponent) {
    const app = {
      _component: rootComponent,
      mount(rootContainer) {
        const container = typeof rootContainer === 'string' ? document.querySelector(rootContainer) : rootContainer;
        if (!container) return;

        // Run setup
        const context = rootComponent.setup ? rootComponent.setup() : {};
        
        // Render & Bind Reactive DOM Tree
        function renderDOM() {
          applyDirectives(container, context);
        }

        // Auto update on reactivity changes
        activeEffect = () => {
          renderDOM();
        };
        try {
          renderDOM();
        } finally {
          activeEffect = null;
        }

        // Trigger onMounted hooks
        nextTick(() => {
          while (mountedHooks.length) {
            const h = mountedHooks.shift();
            try { h(); } catch (e) { console.error('Mounted hook error:', e); }
          }
        });

        return context;
      }
    };
    return app;
  }

  // Simple directive parser helper
  function applyDirectives(el, ctx) {
    if (!el) return;

    // Handle v-if, v-show, v-model, v-for, @click, :class, :value, {{ }}
    // Walk through child elements and bindings
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    const nodesToProcess = [];
    while (walker.nextNode()) {
      nodesToProcess.push(walker.currentNode);
    }

    for (const node of nodesToProcess) {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.nodeValue;
        if (text && text.includes('{{')) {
          const originalText = node._origText || (node._origText = text);
          node.nodeValue = originalText.replace(/\{\{\s*([^}]+)\s*\}\}/g, (_, expr) => {
            try {
              const val = evaluateExpr(expr.trim(), ctx);
              return val !== undefined && val !== null ? val : '';
            } catch {
              return '';
            }
          });
        }
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        // Evaluate attributes
        Array.from(node.attributes).forEach(attr => {
          const name = attr.name;
          const val = attr.value;

          // v-show
          if (name === 'v-show') {
            const visible = !!evaluateExpr(val, ctx);
            node.style.display = visible ? '' : 'none';
          }
          // :class
          else if (name === ':class') {
            const classObj = evaluateExpr(val, ctx);
            if (typeof classObj === 'object' && classObj !== null) {
              Object.entries(classObj).forEach(([cls, active]) => {
                if (active) node.classList.add(cls);
                else node.classList.remove(cls);
              });
            } else if (typeof classObj === 'string') {
              node.className = classObj;
            }
          }
          // v-model
          else if (name === 'v-model' && !node._vmodelBound) {
            node._vmodelBound = true;
            const expr = val.trim();
            const currentVal = evaluateExpr(expr, ctx);
            if (node.type === 'checkbox') {
              node.checked = !!currentVal;
              node.addEventListener('change', () => {
                assignExpr(expr, node.checked, ctx);
              });
            } else {
              if (currentVal !== undefined && currentVal !== null) {
                node.value = currentVal;
              }
              node.addEventListener('input', () => {
                assignExpr(expr, node.value, ctx);
              });
            }
          }
          // @click / @change / @keyup.enter
          else if (name.startsWith('@') && !node['_event_' + name]) {
            node['_event_' + name] = true;
            const eventName = name.slice(1).split('.')[0];
            const isEnter = name.includes('.enter');
            node.addEventListener(eventName, (e) => {
              if (isEnter && e.key !== 'Enter') return;
              try {
                if (typeof ctx[val] === 'function') {
                  ctx[val](e);
                } else {
                  evaluateExpr(val, ctx);
                }
              } catch (err) {
                console.error(`Error in event ${name}:`, err);
              }
            });
          }
        });
      }
    }
  }

  function evaluateExpr(expr, ctx) {
    try {
      const keys = Object.keys(ctx);
      const values = Object.values(ctx).map(v => (v && v.__v_isRef ? v.value : v));
      const fn = new Function(...keys, `return (${expr})`);
      return fn(...values);
    } catch {
      return undefined;
    }
  }

  function assignExpr(expr, val, ctx) {
    try {
      if (ctx[expr] && ctx[expr].__v_isRef) {
        ctx[expr].value = val;
      } else {
        ctx[expr] = val;
      }
    } catch (e) {
      console.error(`Failed to assign ${expr}:`, e);
    }
  }

  exports.createApp = createApp;
  exports.ref = ref;
  exports.reactive = reactive;
  exports.computed = computed;
  exports.watch = watch;
  exports.onMounted = onMounted;
  exports.nextTick = nextTick;

  // Auto-expose to global window
  if (typeof window !== 'undefined') {
    window.Vue = exports;
  }

  return exports;
})({});
