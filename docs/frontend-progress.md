\# RAHAT — Frontend Development Progress



\*\*Date:\*\* October 20, 2026  

\*\*Component:\*\* Flutter Mobile Application  

\*\*Status:\*\* Initial frontend screens implemented; backend integration pending.



\## 1. Project Overview



RAHAT is a disaster-relief coordination application designed initially for flood emergencies in Nepal. Its goal is to help affected communities report needs, track requests, and access relief-related information.



This development phase focused on building the Flutter frontend and implementing local request storage.



\## 2. Technologies Used



\- Flutter

\- Dart

\- Material 3

\- Shared Preferences for local persistence

\- Git and GitHub for version control



\## 3. Features Implemented



\### 3.1 Home Screen



\- Added RAHAT branding and navigation.

\- Added an emergency information banner.

\- Added action cards for Request Help, Track Request, and Relief Map.

\- Added bottom navigation for Home, Requests, and Map.

\- Added a placeholder for the relief overview.



\### 3.2 Request Help



\- Connected the Home screen to the request form.

\- Added a workflow for entering assistance requirements, urgency, location, and description.

\- Connected form submission to the request review screen.



\### 3.3 Request Review and Local Saving



\- Implemented a request review screen displaying the entered details.

\- Added a Save Request button.

\- Generated a unique request identifier using a timestamp.

\- Saved request details locally using Shared Preferences.

\- Assigned the initial status `Pending`.

\- Redirected the user to the tracking screen after saving.



\### 3.4 Track Request



\- Added a screen to retrieve and display locally saved requests.

\- Displayed request information, including identifier, assistance type, urgency, location, description, creation time, and status.

\- Added a refresh control and an empty state.



\*\*Current limitation:\*\* Request data is stored locally in the browser/device. It is not yet synchronized with a central server or shared with relief coordinators.



\### 3.5 Relief Map



\- Created the initial Relief Map screen.

\- Added a map-style visual preview with illustrative markers for relief centers, flood risks, and blocked roads.

\- Added a map legend and an informational notice.

\- Connected the screen to both the Home screen's Relief Map card and the bottom Map navigation item.



\*\*Current limitation:\*\* The map is a visual placeholder. It does not display real geographic tiles, verified locations, or live road conditions.



\## 4. Navigation Flow



Home → Request Help → Request Form → Review Request → Save Request → Track Request



Home → Track Request



Home → Relief Map



Bottom navigation also provides access to Requests and Map.



\## 5. Testing Performed



\- Ran Flutter's static analyzer during development.

\- Ran the application in Chrome.

\- Tested the request form and review workflow.

\- Verified that saving a request opens the tracking screen and displays the saved request.

\- Connected and tested the Relief Map navigation.



\## 6. Remaining Work



1\. Develop an interactive geographic map.

2\. Coordinate with the backend developer on API endpoints and response formats.

3\. Integrate request submission and retrieval with the backend.

4\. Replace local-only request storage with server synchronization when available.

5\. Display verified relief centers and reported hazards from reliable data sources.

6\. Explore offline support and AI-assisted resource allocation and route planning.



\## 7. Important Limitations



\- Local requests are not visible to other users or relief coordinators.

\- Request statuses are not updated by a backend.

\- Map markers are illustrative, not verified emergency information.

\- Live notifications, real-time coordination, and AI-based routing have not been implemented.



\## 8. Development Commands



Run these commands from the `mobile` directory:



```powershell

D:\\Apps\\flutter\\bin\\flutter.bat analyze

D:\\Apps\\flutter\\bin\\flutter.bat run -d chrome

```



\## 9. Version Control



The source code is maintained in the RAHAT Git repository. Keep this document updated as frontend features are implemented and backend integration progresses.

