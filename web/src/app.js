import React, { useEffect, useState } from 'react';
import {
  HashRouter as Router,
  Routes,
  Route,
  NavLink
} from "react-router-dom";
import { QueryParamProvider } from 'use-query-params';
import { ReactRouter6Adapter } from 'use-query-params/adapters/react-router-6';

import { library } from '@fortawesome/fontawesome-svg-core'
import { fas } from '@fortawesome/free-solid-svg-icons'
import { far } from '@fortawesome/free-regular-svg-icons'
import { fab } from '@fortawesome/free-brands-svg-icons'

import './main.css';
import {
  updateComponentLibrary,
  checkForComponentLibraryUpdate,
  hasLocalComponentLibrary,
  db
} from './db'
import { ComponentOverview } from './componentTable'
import { CompareParts } from './compare'


library.add(fas, far, fab);

let activeLibraryUpdate = null;

function runComponentLibraryUpdate(onProgress) {
  if (activeLibraryUpdate === null) {
    const progressListeners = new Set();
    const startedAt = performance.now();
    const promise = updateComponentLibrary(progress => {
      for (const listener of progressListeners) {
        listener(progress);
      }
    }).then(() => {
      let finishedAt = performance.now();
      console.log("Library update took ", finishedAt - startedAt, "ms");
    }).finally(() => {
      activeLibraryUpdate = null;
    });
    activeLibraryUpdate = { progressListeners, promise };
  }

  activeLibraryUpdate.progressListeners.add(onProgress);
  return {
    promise: activeLibraryUpdate.promise,
    unsubscribe: () => activeLibraryUpdate?.progressListeners.delete(onProgress),
  };
}

function Header(props) {
  return <>
    <div className="w-full px-2 py-8 flex">
      <img src="./favicon.svg" alt="" className="block flex-none mr-4 h-auto"/>
      <div className="flex-1">
        <h1 className="text-4xl font-bold">
          JLC PCB SMD Assembly Component Catalogue
        </h1>
        <p>
          Parametric search for components offered by <a href="https://jlcpcb.com/smt-assembly?from=JanMrazek" className="underline text-blue-600">JLC PCB SMD assembly service</a>.
        </p>
        <p>
          Read more at project's <a className="underline text-blue-500 hover:text-blue-800" href="https://github.com/yaqwsx/jlcparts">GitHub page</a>.
        </p>
      </div>
    </div>
    <div className="rounded my-3 p-2 border-blue-500 border-2">
      Do you enjoy this site? Consider supporting me so I can actively maintain projects like this one!
      Read more about <a className="underline text-blue-500 hover:text-blue-800" href="https://github.com/sponsors/yaqwsx">my story</a>.
      <table>
        <tbody>
          <tr>
            <td className="pr-2 text-right">
              GitHub Sponsors:
            </td>
            <td>
              <iframe src="https://github.com/sponsors/yaqwsx/button" title="Sponsor yaqwsx" height="35" width="116" style={{border: 0}} className="inline-block"></iframe>
            </td>
          </tr>
          <tr>
            <td className="pr-2 text-right">
              Ko-Fi:
            </td>
            <td>
              <a href="https://ko-fi.com/E1E2181LU">
                <img src="https://ko-fi.com/img/githubbutton_sm.svg" alt="Ko-Fi button" className="inline-block"/>
              </a>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </>
}

function Footer(props) {
  return <div className="w-full p-2 border-t-2 border-gray-800" style={{minHeight: "200px"}}>

  </div>
}

function FirstTimeNote() {
  const [hasLibrary, setHasLibrary] = useState(undefined);

  useEffect(() => {
    let cancelled = false;
    hasLocalComponentLibrary().then(hasLibrary => {
      if (!cancelled) {
        setHasLibrary(hasLibrary);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (hasLibrary === undefined || hasLibrary)
    return null;
  return <div className="w-full p-8 my-2 bg-yellow-400 rounded">
      <p>
        Hey, it seems that you run the application for the first time, hence,
        there's no component library in your device. Just press the "Update
        the component library button" in the upper right corner to download it
        and use the app.
      </p>
      <p>
        The initial metadata download is small, and component shards are cached on demand.
      </p>
    </div>
}

function UpdateBar({ onTriggerUpdate }) {
  const [updateAvailable, setUpdateAvailable] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(undefined);

  useEffect(() => {
    let cancelled = false;
    let checkStatus = () => {
      checkForComponentLibraryUpdate().then( updateAvailable => {
        if (!cancelled) {
          setUpdateAvailable(updateAvailable);
        }
      });
      db.settings.get("lastUpdate").then(lastUpdate => {
        if (!cancelled) {
          setLastUpdate(lastUpdate?.value);
        }
      })
    };

    checkStatus();
    const timerID = setInterval(checkStatus, 60000);
    return () => {
      cancelled = true;
      clearInterval(timerID);
    };
  }, []);

  const handleUpdateClick = e => {
    e.preventDefault();
    onTriggerUpdate();
  }

  if (updateAvailable) {
    return <div className="flex flex-wrap w-full align-middle bg-yellow-400 p-2">
                <p className="inline-block w-full md:w-1/2 py-2">There is an update of the component library available.</p>
                <button className="inline-block w-full md:w-1/2 bg-green-500 hover:bg-green-600 py-2 px-4 rounded"
                        onClick={handleUpdateClick}>
                  Update the component library
                </button>
              </div>
  }
  return <div className="w-full bg-green-400 p-2 text-xs">
            <p>The component database is up to-date {lastUpdate ? `(${lastUpdate})` : ""}.</p>
          </div>
}

function renderProgress(status) {
  if (status.length < 3)
    return null;
  let progress = status[2];
  if (progress === null) {
    return <div className="w-full bg-gray-300 mt-2 h-2">
      <div className="bg-blue-500 h-2" style={{width: "50%"}}></div>
    </div>
  }
  let width = Math.max(0, Math.min(100, progress * 100));
  return <div className="w-full bg-gray-300 mt-2 h-2">
    <div className="bg-blue-500 h-2" style={{width: `${width}%`}}></div>
  </div>
}

function Updater({ onFinish }) {
  const [progress, setProgress] = useState({});

  useEffect(() => {
    let cancelled = false;
    const update = runComponentLibraryUpdate(nextProgress => {
      if (!cancelled) {
        setProgress(nextProgress);
      }
    });
    update.promise.then(() => {
      if (!cancelled) {
        onFinish();
      }
    });
    return () => {
      cancelled = true;
      update.unsubscribe();
    };
  }, [onFinish]);

  const listItems = () => {
    let items = []
    for (const [task, status] of Object.entries(progress)) {
      let color = status[1] ? "bg-green-500" : "bg-yellow-400";
      items.push(<tr key={task}>
        <td className="p-2">{task}</td>
        <td className={`p-2 ${color}`}>
          {status[0]}
          {renderProgress(status)}
        </td>
      </tr>)
    }
    return items;
  }

  return <div className="w-full px-2 py-8">
      <h1 className="font-bold text-2xl">Update progress:</h1>
      <table className="w-full">
        <thead>
          <tr className="border-b-2 border-gray-800 font-bold">
            <td>Operation/category</td>
            <td>Progress</td>
          </tr>
        </thead>
        <tbody>
          {listItems()}
        </tbody>
      </table>
    </div>
}

function Container(props) {
  return <div className="container mx-auto px-2">{props.children}</div>
}

function Navbar() {
  const navClassName = ({ isActive }) =>
    `inline-block p-4 bg-white${isActive ? " bg-gray-200 font-bold" : ""}`;
  return <div className="w-ful text-lg">
    <NavLink to="/" end className={navClassName}>
      Component search
    </NavLink>
    <NavLink to="/compare" className={navClassName}>
      Compare parts
    </NavLink>
  </div>
}

export function NoMatch() {
  return <p>404 not found</p>;
}

function App() {
  const [updating, setUpdating] = useState(false);

  if (updating) {
    return <Container>
      <Updater onFinish={() => setUpdating(false)}/>
    </Container>
  }
  return (
    <Router basename="/" >
      <Container>
        <UpdateBar onTriggerUpdate={() => setUpdating(true)}/>
        <Header/>
        <FirstTimeNote/>
        <Navbar/>
          <QueryParamProvider adapter={ReactRouter6Adapter}>
            <Routes>
                <Route path="/" element={<ComponentOverview/>} />
                <Route path="/compare" element={<CompareParts/>} />
                <Route path="*" element={<NoMatch />} />
            </Routes>
          </QueryParamProvider>
        <Footer/>
      </Container>
    </Router>
  );
}

export default App;
